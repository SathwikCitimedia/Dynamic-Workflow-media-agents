from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import HTTPException, status

from app.agent_client import AgentClient, AgentClientError
from app.config import settings
from app.models import (
    WorkflowSession,
    WorkflowStep,
    AgentDefinition,
    ApproveWorkflowNodeRequest,
    CancelWorkflowRunRequest,
    CreateWorkflowRunRequest,
    DynamicFrontendCard,
    DynamicWorkflowGraph,
    DynamicWorkflowGraphEdge,
    DynamicWorkflowGraphNode,
    DynamicWorkflowProgress,
    StepStatus,
    WorkflowBundle,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunBundle,
    WorkflowRunStateResponse,
    WorkflowStatus,
    new_id,
    utc_now,
)
from app.output_mapper import extract_useful_content, map_for_geo_fence, map_for_media_planner, map_for_meta
from app.repositories.base import BaseDynamicRepository, DynamicEntityNotFoundError
from app.seed.media_workflow import DEFAULT_MEDIA_WORKFLOW_ID, MEDIA_AGENT_IDS
from app.services.dag_service import DagService
from app.services.template_service import render_template
from app.websocket_manager import WebSocketManager


class WorkflowRunService:
    def __init__(
        self,
        repository: BaseDynamicRepository,
        agent_client: AgentClient,
        dag_service: DagService,
        websocket_manager: WebSocketManager | None = None,
    ) -> None:
        self._repository = repository
        self._agent_client = agent_client
        self._dag_service = dag_service
        self._websocket_manager = websocket_manager
        self._tasks: set[asyncio.Task[Any]] = set()
        self._allow_mock_fallback = settings.allow_agent_mock_fallback and isinstance(agent_client, AgentClient)

    async def create_run(self, request: CreateWorkflowRunRequest) -> WorkflowRunBundle:
        bundle = await self._get_workflow_bundle(request.workflow_id)
        if not bundle.workflow.enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow is disabled.")

        run = WorkflowRun(
            id=new_id("run"),
            workflow_id=request.workflow_id,
            status=WorkflowStatus.RUNNING,
            initial_input_json=request.input,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        node_runs = {
            node.node_key: WorkflowNodeRun(
                id=new_id("node_run"),
                workflow_run_id=run.id,
                node_key=node.node_key,
                agent_id=node.agent_id,
                status=StepStatus.PENDING,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            for node in bundle.nodes
        }
        created = await self._repository.create_workflow_run_bundle(WorkflowRunBundle(run=run, node_runs=node_runs))
        start_nodes = self._dag_service.start_node_keys(bundle)
        if start_nodes:
            async def mark_start_nodes_running(working: WorkflowRunBundle) -> WorkflowRunBundle:
                for node_key in start_nodes:
                    working.node_runs[node_key].status = StepStatus.RUNNING
                    working.node_runs[node_key].updated_at = utc_now()
                working.run.status = WorkflowStatus.RUNNING
                working.run.updated_at = utc_now()
                return working

            created = await self._repository.update_workflow_run_bundle(run.id, mark_start_nodes_running)
        if start_nodes:
            self._schedule_parallel_nodes(created.run.id, start_nodes)
        return await self.get_run(created.run.id)

    async def list_runs(self) -> list[WorkflowRunBundle]:
        return await self._repository.list_workflow_run_bundles()

    async def get_run(self, run_id: str) -> WorkflowRunBundle:
        try:
            bundle = await self._repository.get_workflow_run_bundle(run_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.") from exc
        return await self._recalculate_run_status(bundle)

    async def approve_node(
        self,
        run_id: str,
        node_key: str,
        request: ApproveWorkflowNodeRequest | None = None,
    ) -> WorkflowRunBundle:
        current = await self.get_run(run_id)
        if current.run.status == WorkflowStatus.CANCELLED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow run is cancelled.")
        node_run = self._require_node_run(current, node_key)
        if node_run.status != StepStatus.WAITING_FOR_APPROVAL:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Node is not waiting for approval.")

        approved_output = request.approved_output if request and request.approved_output is not None else extract_useful_content(node_run.raw_output_json)

        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            target = working.node_runs[node_key]
            target.status = StepStatus.APPROVED
            target.approved_output_json = approved_output
            target.error = None
            target.updated_at = utc_now()
            return working

        updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        updated = await self._recalculate_run_status(updated)
        await self._emit_event("NODE_APPROVED", updated, node_key)
        await self._start_runnable_children(updated, node_key)
        return await self.get_run(run_id)

    async def reject_node(self, run_id: str, node_key: str, reason: str) -> WorkflowRunBundle:
        current = await self.get_run(run_id)
        if current.run.status == WorkflowStatus.CANCELLED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow run is cancelled.")
        node_run = self._require_node_run(current, node_key)
        if node_run.status != StepStatus.WAITING_FOR_APPROVAL:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Node is not waiting for approval.")
        regenerated_task = self._build_regeneration_task(node_run.input_task or "", node_run.raw_output_json, reason)

        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            target = working.node_runs[node_key]
            target.user_feedback_history_json.append(reason)
            target.rejection_reason = reason
            target.revision_count += 1
            target.status = StepStatus.RUNNING
            target.input_task = regenerated_task
            target.approved_output_json = None
            target.error = None
            target.updated_at = utc_now()
            return working

        updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        updated = await self._recalculate_run_status(updated)
        await self._emit_event("NODE_REJECTED_REGENERATING", updated, node_key, {"reason": reason})
        self._schedule_node_run(run_id, node_key, regenerated_task)
        return updated

    async def retry_node(self, run_id: str, node_key: str) -> WorkflowRunBundle:
        current = await self.get_run(run_id)
        node_run = self._require_node_run(current, node_key)
        if node_run.status != StepStatus.FAILED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Node is not failed.")
        if not node_run.input_task:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Node does not have an original task.")

        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            target = working.node_runs[node_key]
            target.status = StepStatus.RUNNING
            target.error = None
            target.updated_at = utc_now()
            return working

        updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        updated = await self._recalculate_run_status(updated)
        await self._emit_event("NODE_STARTED", updated, node_key, {"retry": True})
        self._schedule_node_run(run_id, node_key, node_run.input_task)
        return updated

    async def cancel_run(self, run_id: str, request: CancelWorkflowRunRequest) -> WorkflowRunBundle:
        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            working.run.status = WorkflowStatus.CANCELLED
            working.run.updated_at = utc_now()
            for node_run in working.node_runs.values():
                if node_run.status == StepStatus.PENDING:
                    node_run.status = StepStatus.CANCELLED
                    node_run.error = request.reason
                    node_run.updated_at = utc_now()
            return working

        try:
            updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.") from exc
        await self._emit_workflow_terminal_event(updated)
        return updated

    async def build_run_response(self, run_id: str) -> WorkflowRunStateResponse:
        run_bundle = await self.get_run(run_id)
        workflow_bundle = await self._get_workflow_bundle(run_bundle.run.workflow_id)
        return WorkflowRunStateResponse(
            run=run_bundle.run,
            current_stage=self.get_current_stage(run_bundle, workflow_bundle),
            progress=self.build_progress(run_bundle),
            frontend_cards=self.build_frontend_cards(run_bundle, workflow_bundle),
            workflow_graph=self.build_workflow_graph(run_bundle, workflow_bundle),
            available_actions=[] if run_bundle.run.status in {WorkflowStatus.CANCELLED, WorkflowStatus.COMPLETED} else ["cancel"],
            node_runs=run_bundle.node_runs,
        )

    def get_current_stage(self, run_bundle: WorkflowRunBundle, workflow_bundle: WorkflowBundle) -> str:
        if run_bundle.run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}:
            return run_bundle.run.status.value
        ordered_keys = [node.node_key for node in workflow_bundle.nodes]
        for node_key in ordered_keys:
            status_value = run_bundle.node_runs[node_key].status
            if status_value in {StepStatus.RUNNING, StepStatus.WAITING_FOR_APPROVAL, StepStatus.FAILED}:
                return node_key.upper()
        for node_key in ordered_keys:
            if run_bundle.node_runs[node_key].status == StepStatus.PENDING:
                return node_key.upper()
        return "RUNNING"

    def build_progress(self, run_bundle: WorkflowRunBundle) -> DynamicWorkflowProgress:
        completed = {StepStatus.APPROVED, StepStatus.SKIPPED}
        return DynamicWorkflowProgress(
            total_nodes=len(run_bundle.node_runs),
            completed_nodes=sum(1 for node_run in run_bundle.node_runs.values() if node_run.status in completed),
            waiting_for_approval_nodes=[
                node_key for node_key, node_run in run_bundle.node_runs.items() if node_run.status == StepStatus.WAITING_FOR_APPROVAL
            ],
            running_nodes=[node_key for node_key, node_run in run_bundle.node_runs.items() if node_run.status == StepStatus.RUNNING],
            failed_nodes=[
                node_key
                for node_key, node_run in run_bundle.node_runs.items()
                if node_run.status in {StepStatus.FAILED, StepStatus.CANCELLED}
            ],
        )

    def build_frontend_cards(
        self,
        run_bundle: WorkflowRunBundle,
        workflow_bundle: WorkflowBundle,
    ) -> list[DynamicFrontendCard]:
        node_map = {node.node_key: node for node in workflow_bundle.nodes}
        cards: list[DynamicFrontendCard] = []
        for node in workflow_bundle.nodes:
            node_run = run_bundle.node_runs[node.node_key]
            output = node_run.approved_output_json if node_run.approved_output_json is not None else node_run.raw_output_json
            summary = ""
            if isinstance(output, dict):
                if isinstance(output.get("text"), str) and output["text"]:
                    summary = output["text"]
                elif isinstance(output.get("content"), str):
                    summary = output["content"]
                else:
                    summary = json.dumps(output, ensure_ascii=True)[:240]
            elif isinstance(output, str):
                summary = output
            elif output is not None:
                summary = json.dumps(output, ensure_ascii=True)[:240]
            elif node_run.error:
                summary = node_run.error
            cards.append(
                DynamicFrontendCard(
                    node_key=node.node_key,
                    title=node_map[node.node_key].display_name,
                    status=node_run.status,
                    summary=summary,
                    output=output if output is not None else {},
                    mapped_input_preview=node_run.mapped_input_preview,
                    available_actions=self.get_node_available_actions(node_run),
                )
            )
        return cards

    def build_workflow_graph(
        self,
        run_bundle: WorkflowRunBundle,
        workflow_bundle: WorkflowBundle,
    ) -> DynamicWorkflowGraph:
        return DynamicWorkflowGraph(
            nodes=[
                DynamicWorkflowGraphNode(
                    id=node.node_key,
                    label=node.display_name,
                    status=run_bundle.node_runs[node.node_key].status,
                )
                for node in workflow_bundle.nodes
            ],
            edges=[
                DynamicWorkflowGraphEdge(**{"from": edge.source_node_key, "to": edge.target_node_key})
                for edge in workflow_bundle.edges
            ],
        )

    def get_node_available_actions(self, node_run: WorkflowNodeRun) -> list[str]:
        if node_run.status == StepStatus.WAITING_FOR_APPROVAL:
            return ["approve", "reject"]
        if node_run.status == StepStatus.FAILED:
            return ["retry"]
        return []

    async def _start_runnable_children(self, run_bundle: WorkflowRunBundle, approved_node_key: str) -> None:
        workflow_bundle = await self._get_workflow_bundle(run_bundle.run.workflow_id)
        to_start: list[str] = []
        for edge in self._dag_service.child_edges(workflow_bundle, approved_node_key):
            child_run = run_bundle.node_runs[edge.target_node_key]
            if child_run.status != StepStatus.PENDING:
                continue
            parents = self._dag_service.parent_edges(workflow_bundle, edge.target_node_key)
            if all(run_bundle.node_runs[parent.source_node_key].status == StepStatus.APPROVED for parent in parents):
                to_start.append(edge.target_node_key)
        if to_start:
            self._schedule_parallel_nodes(run_bundle.run.id, to_start)

    def _schedule_parallel_nodes(self, run_id: str, node_keys: list[str]) -> None:
        task = asyncio.create_task(self._execute_parallel_nodes(run_id, node_keys))
        self._track_task(task)

    def _schedule_node_run(self, run_id: str, node_key: str, task_override: str | None) -> None:
        task = asyncio.create_task(self._execute_node(run_id, node_key, task_override))
        self._track_task(task)

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _execute_parallel_nodes(self, run_id: str, node_keys: list[str]) -> None:
        await asyncio.gather(*(self._execute_node(run_id, node_key, None) for node_key in node_keys))

    async def _execute_node(self, run_id: str, node_key: str, task_override: str | None) -> None:
        try:
            run_bundle = await self.get_run(run_id)
            if run_bundle.run.status == WorkflowStatus.CANCELLED:
                return
            workflow_bundle = await self._get_workflow_bundle(run_bundle.run.workflow_id)
            node_definition = next(node for node in workflow_bundle.nodes if node.node_key == node_key)
            agent = await self._get_agent(node_definition.agent_id)
            mapped_input = self._build_mapped_input(run_bundle, workflow_bundle, node_key)
            input_payload = self._build_input_payload(
                run_bundle=run_bundle,
                node_run=run_bundle.node_runs[node_key],
                node_key=node_key,
                node_definition=node_definition,
                mapped_input=mapped_input,
                task_override=task_override,
            )
            task_text = input_payload.get("task")
            if not isinstance(task_text, str) or not task_text.strip():
                raise AgentClientError(f"Node '{node_key}' did not render a valid task.")

            async def mark_running(working: WorkflowRunBundle) -> WorkflowRunBundle:
                target = working.node_runs[node_key]
                target.status = StepStatus.RUNNING
                target.input_task = task_text
                target.input_payload_json = input_payload
                target.mapped_input_preview = mapped_input if settings.debug_workflow_payloads else None
                target.error = None
                target.updated_at = utc_now()
                return working

            running_bundle = await self._repository.update_workflow_run_bundle(run_id, mark_running)
            running_bundle = await self._recalculate_run_status(running_bundle)
            await self._emit_event("NODE_STARTED", running_bundle, node_key)

            response = await self._execute_registered_or_legacy_agent(
                agent=agent,
                run_bundle=run_bundle,
                node_key=node_key,
                task_text=task_text,
                mapped_input=mapped_input,
            )
            next_agent_session_id = response.pop("agent_session_id", None) if isinstance(response, dict) else None

            async def mark_complete(working: WorkflowRunBundle) -> WorkflowRunBundle:
                target = working.node_runs[node_key]
                target.raw_output_json = response
                target.error = None
                target.agent_session_id = next_agent_session_id or target.agent_session_id
                target.updated_at = utc_now()
                if node_definition.approval_required:
                    target.status = StepStatus.WAITING_FOR_APPROVAL
                else:
                    target.status = StepStatus.APPROVED
                    target.approved_output_json = extract_useful_content(response)
                return working

            completed_bundle = await self._repository.update_workflow_run_bundle(run_id, mark_complete)
            completed_bundle = await self._recalculate_run_status(completed_bundle)
            await self._emit_event("NODE_COMPLETED", completed_bundle, node_key)
            if node_definition.approval_required:
                await self._emit_event("NODE_WAITING_APPROVAL", completed_bundle, node_key)
            else:
                await self._emit_event("NODE_APPROVED", completed_bundle, node_key, {"auto_approved": True})
                await self._start_runnable_children(completed_bundle, node_key)
            await self._emit_workflow_terminal_event(completed_bundle)
        except Exception as exc:  # pragma: no cover - async defensive path
            if isinstance(exc, HTTPException):
                raise
            if self._allow_mock_fallback:
                await self._mark_mock_fallback(run_id, node_key, str(exc))
            else:
                await self._mark_failed(run_id, node_key, str(exc))

    def _build_input_payload(
        self,
        *,
        run_bundle: WorkflowRunBundle,
        node_run: WorkflowNodeRun,
        node_key: str,
        node_definition,
        mapped_input: dict[str, Any],
        task_override: str | None,
    ) -> dict[str, Any]:
        parent_outputs = self._parent_outputs(run_bundle, run_bundle.run.workflow_id, node_key)
        task_value = task_override or node_definition.input_template_json.get("task", "")
        context = {
            "initial_input": run_bundle.run.initial_input_json,
            "mapped_input": mapped_input,
            "parent_outputs": parent_outputs,
            "task": task_value,
            "agent_session_id": node_run.agent_session_id,
            "current_node": {"node_key": node_definition.node_key, "display_name": node_definition.display_name},
        }
        rendered_template = render_template(node_definition.input_template_json, context)
        if task_override:
            rendered_template["task"] = task_override
        return rendered_template

    def _build_mapped_input(self, run_bundle: WorkflowRunBundle, workflow_bundle: WorkflowBundle, node_key: str) -> dict[str, Any]:
        if workflow_bundle.workflow.id == DEFAULT_MEDIA_WORKFLOW_ID:
            legacy_session = self._build_seeded_media_session(run_bundle)
            if node_key == "media_planner":
                return map_for_media_planner(legacy_session)
            if node_key == "geo_fence":
                return {
                    "url": str(legacy_session.url),
                    "media_plan": extract_useful_content(legacy_session.steps["media_planner"].approved_output),
                }
            if node_key == "meta":
                return {
                    "url": str(legacy_session.url),
                    "media_plan": extract_useful_content(legacy_session.steps["media_planner"].approved_output),
                }
        mapped_input: dict[str, Any] = {}
        for edge in self._dag_service.parent_edges(workflow_bundle, node_key):
            source_run = run_bundle.node_runs[edge.source_node_key]
            for target_key, expression in edge.mapping_json.items():
                mapped_input[target_key] = self._resolve_mapping_expression(
                    expression,
                    source_run=source_run,
                    run=run_bundle.run,
                )
        return mapped_input

    def _resolve_mapping_expression(
        self,
        expression: Any,
        *,
        source_run: WorkflowNodeRun,
        run: WorkflowRun,
    ) -> Any:
        if not isinstance(expression, str):
            return expression
        if not expression.startswith("$."):
            return expression
        current: Any
        if expression.startswith("$.initial_input."):
            current = run.initial_input_json
            parts = expression[len("$.initial_input."):].split(".")
        else:
            current = {
                "approved_output": source_run.approved_output_json,
                "raw_output": source_run.raw_output_json,
                "input_payload": source_run.input_payload_json,
                "input_task": source_run.input_task,
            }
            parts = expression[2:].split(".")
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            return None
        return current

    def _parent_outputs(self, run_bundle: WorkflowRunBundle, workflow_id: str, node_key: str) -> dict[str, Any]:
        del workflow_id
        return {
            key: {
                "approved_output": node_run.approved_output_json,
                "raw_output": node_run.raw_output_json,
                "status": node_run.status.value,
            }
            for key, node_run in run_bundle.node_runs.items()
            if key != node_key
        }

    async def _execute_registered_or_legacy_agent(
        self,
        *,
        agent: AgentDefinition,
        run_bundle: WorkflowRunBundle,
        node_key: str,
        task_text: str,
        mapped_input: dict[str, Any],
    ) -> dict[str, Any]:
        if hasattr(self._agent_client, "run_registered_agent"):
            return await self._agent_client.run_registered_agent(
                agent,
                context={
                    "task": task_text,
                    "agent_session_id": run_bundle.node_runs[node_key].agent_session_id,
                    "initial_input": run_bundle.run.initial_input_json,
                    "mapped_input": mapped_input,
                    "node_key": node_key,
                },
            )

        legacy_agent = self._legacy_agent_settings_for_node(node_key)
        user_id = run_bundle.run.initial_input_json.get("user_id", settings.agent_user_id)
        return await self._agent_client.run_agent(
            legacy_agent,
            task_text,
            user_id,
            run_bundle.node_runs[node_key].agent_session_id,
        )

    def _legacy_agent_settings_for_node(self, node_key: str):
        mapping = {
            "atlas": settings.atlas,
            "audit": settings.audit,
            "media_planner": settings.media_planner,
            "geo_fence": settings.geo_fence,
            "meta": settings.meta,
        }
        if node_key not in mapping:
            raise AgentClientError(f"No legacy agent mapping exists for node '{node_key}'.")
        return mapping[node_key]

    def _build_seeded_media_session(self, run_bundle: WorkflowRunBundle) -> WorkflowSession:
        steps: dict[str, WorkflowStep] = {}
        for node_key in MEDIA_AGENT_IDS:
            node_run = run_bundle.node_runs[node_key]
            steps[node_key] = WorkflowStep(
                session_id=run_bundle.run.id,
                step_id=node_key,
                status=node_run.status,
                agent_session_id=node_run.agent_session_id,
                input_task=node_run.input_task,
                mapped_input_preview=node_run.mapped_input_preview,
                raw_output=node_run.raw_output_json,
                approved_output=node_run.approved_output_json,
                user_feedback_history=list(node_run.user_feedback_history_json),
                rejection_reason=node_run.rejection_reason,
                revision_count=node_run.revision_count,
                error=node_run.error,
                available_actions=[],
                updated_at=node_run.updated_at,
            )
        return WorkflowSession(
            session_id=run_bundle.run.id,
            url=run_bundle.run.initial_input_json["url"],
            user_id=run_bundle.run.initial_input_json.get("user_id", settings.agent_user_id),
            steps=steps,
            workflow_status=run_bundle.run.status,
            updated_at=run_bundle.run.updated_at,
        )

    async def _mark_failed(self, run_id: str, node_key: str, error_message: str) -> None:
        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            target = working.node_runs[node_key]
            target.status = StepStatus.FAILED
            target.error = error_message
            target.updated_at = utc_now()
            return working

        updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        updated = await self._recalculate_run_status(updated)
        await self._emit_event("NODE_FAILED", updated, node_key, {"error": error_message})
        await self._emit_workflow_terminal_event(updated)

    async def _mark_mock_fallback(self, run_id: str, node_key: str, error_message: str) -> None:
        mock_output = {
            "content": f"Mock fallback output for {node_key}. Real agent call failed: {error_message}",
            "is_mock": True,
            "original_error": error_message,
        }

        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            target = working.node_runs[node_key]
            target.raw_output_json = mock_output
            target.error = error_message
            target.status = StepStatus.WAITING_FOR_APPROVAL
            target.updated_at = utc_now()
            return working

        updated = await self._repository.update_workflow_run_bundle(run_id, updater)
        updated = await self._recalculate_run_status(updated)
        await self._emit_event("NODE_WAITING_APPROVAL", updated, node_key, {"is_mock": True, "error": error_message})

    async def _emit_event(
        self,
        event_type: str,
        run_bundle: WorkflowRunBundle,
        node_key: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._websocket_manager is None:
            return
        await self._websocket_manager.broadcast(
            run_bundle.run.id,
            {
                "type": event_type,
                "run_id": run_bundle.run.id,
                "node_key": node_key,
                "status": run_bundle.node_runs[node_key].status.value,
                "workflow_status": run_bundle.run.status.value,
                "payload": payload or {},
            },
        )

    async def _emit_workflow_terminal_event(self, run_bundle: WorkflowRunBundle) -> None:
        if self._websocket_manager is None:
            return
        mapping = {
            WorkflowStatus.COMPLETED: "WORKFLOW_COMPLETED",
            WorkflowStatus.CANCELLED: "WORKFLOW_CANCELLED",
            WorkflowStatus.FAILED: "WORKFLOW_FAILED",
        }
        event_type = mapping.get(run_bundle.run.status)
        if event_type is None:
            return
        await self._websocket_manager.broadcast(
            run_bundle.run.id,
            {
                "type": event_type,
                "run_id": run_bundle.run.id,
                "node_key": None,
                "status": None,
                "workflow_status": run_bundle.run.status.value,
                "payload": {},
            },
        )

    async def _recalculate_run_status(self, run_bundle: WorkflowRunBundle) -> WorkflowRunBundle:
        async def updater(working: WorkflowRunBundle) -> WorkflowRunBundle:
            if working.run.status == WorkflowStatus.CANCELLED:
                working.run.updated_at = utc_now()
                return working
            node_statuses = [node_run.status for node_run in working.node_runs.values()]
            if any(status_value == StepStatus.FAILED for status_value in node_statuses):
                working.run.status = WorkflowStatus.FAILED
            elif all(status_value in {StepStatus.APPROVED, StepStatus.SKIPPED} for status_value in node_statuses):
                working.run.status = WorkflowStatus.COMPLETED
            elif any(status_value == StepStatus.WAITING_FOR_APPROVAL for status_value in node_statuses):
                working.run.status = WorkflowStatus.WAITING_FOR_APPROVAL
            else:
                working.run.status = WorkflowStatus.RUNNING
            working.run.updated_at = utc_now()
            return working

        return await self._repository.update_workflow_run_bundle(run_bundle.run.id, updater)

    async def _get_workflow_bundle(self, workflow_id: str) -> WorkflowBundle:
        try:
            return await self._repository.get_workflow_bundle(workflow_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.") from exc

    async def _get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return await self._repository.get_agent(agent_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.") from exc

    def _require_node_run(self, run_bundle: WorkflowRunBundle, node_key: str) -> WorkflowNodeRun:
        node_run = run_bundle.node_runs.get(node_key)
        if node_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node run not found.")
        return node_run

    def _build_regeneration_task(self, original_task: str, previous_output: Any, reason: str) -> str:
        return (
            "The user did not approve the previous output and requested regeneration.\n"
            f"Original task: {original_task}\n"
            f"Previous output: {json.dumps(extract_useful_content(previous_output), ensure_ascii=True)}\n"
            f"Reason: {reason}\n"
            "Generate the revised output."
        )
