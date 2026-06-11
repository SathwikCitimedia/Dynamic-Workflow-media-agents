from __future__ import annotations

from fastapi import HTTPException, status

from app.config import settings
from app.models import (
    ApproveWorkflowNodeRequest,
    CancelWorkflowRunRequest,
    CreateSessionRequest,
    CreateWorkflowRunRequest,
    RecentSessionsResponse,
    RecentSessionSummary,
    RejectWorkflowNodeRequest,
    StepId,
    WorkflowStateResponse,
)
from app.seed.media_workflow import DEFAULT_MEDIA_WORKFLOW_ID
from app.services.legacy_session_adapter import (
    dynamic_recent_runs_to_legacy_recent_sessions,
    dynamic_run_to_legacy_session_response,
    legacy_session_id_to_run_id,
    legacy_step_id_to_node_key,
)
from app.services.workflow_run_service import WorkflowRunService


class WorkflowEngine:
    def __init__(self, workflow_run_service: WorkflowRunService) -> None:
        self._workflow_run_service = workflow_run_service

    async def create_session(self, request: CreateSessionRequest) -> WorkflowStateResponse:
        run_bundle = await self._workflow_run_service.create_run(
            CreateWorkflowRunRequest(
                workflow_id=DEFAULT_MEDIA_WORKFLOW_ID,
                input={
                    "url": str(request.url),
                    "user_id": request.user_id or settings.agent_user_id,
                },
            )
        )
        dynamic_response = await self._workflow_run_service.build_run_response(run_bundle.run.id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    async def get_session(self, session_id: str) -> WorkflowStateResponse:
        run_id = legacy_session_id_to_run_id(session_id)
        dynamic_response = await self._workflow_run_service.build_run_response(run_id)
        self._ensure_media_workflow(dynamic_response.run.workflow_id, session_id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    async def list_recent_sessions(self, limit: int = 6) -> RecentSessionsResponse:
        runs = await self._workflow_run_service.list_runs()
        filtered = sorted(
            [run for run in runs if run.run.workflow_id == DEFAULT_MEDIA_WORKFLOW_ID],
            key=lambda item: item.run.created_at,
            reverse=True,
        )[:limit]
        responses = [await self._workflow_run_service.build_run_response(run.run.id) for run in filtered]
        legacy = dynamic_recent_runs_to_legacy_recent_sessions(responses)
        ordered: list[RecentSessionSummary] = []
        for response, summary in zip(responses, legacy.sessions, strict=False):
            ordered.append(
                RecentSessionSummary(
                    session_id=summary.session_id,
                    url=summary.url,
                    workflow_status=summary.workflow_status,
                    current_stage=summary.current_stage,
                    updated_at=response.run.created_at,
                    progress=summary.progress,
                )
            )
        return RecentSessionsResponse(sessions=ordered)

    async def approve_step(
        self,
        session_id: str,
        step_id: StepId,
        approved_output,
    ) -> WorkflowStateResponse:
        run_id = legacy_session_id_to_run_id(session_id)
        node_key = legacy_step_id_to_node_key(step_id)
        dynamic_bundle = await self._workflow_run_service.approve_node(
            run_id,
            node_key,
            ApproveWorkflowNodeRequest(approved_output=approved_output),
        )
        dynamic_response = await self._workflow_run_service.build_run_response(dynamic_bundle.run.id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    async def reject_step(self, session_id: str, step_id: StepId, reason: str) -> WorkflowStateResponse:
        run_id = legacy_session_id_to_run_id(session_id)
        node_key = legacy_step_id_to_node_key(step_id)
        dynamic_bundle = await self._workflow_run_service.reject_node(
            run_id,
            node_key,
            RejectWorkflowNodeRequest(reason=reason).reason,
        )
        dynamic_response = await self._workflow_run_service.build_run_response(dynamic_bundle.run.id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    async def retry_step(self, session_id: str, step_id: StepId) -> WorkflowStateResponse:
        run_id = legacy_session_id_to_run_id(session_id)
        node_key = legacy_step_id_to_node_key(step_id)
        dynamic_bundle = await self._workflow_run_service.retry_node(run_id, node_key)
        dynamic_response = await self._workflow_run_service.build_run_response(dynamic_bundle.run.id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    async def cancel_workflow(self, session_id: str, reason: str) -> WorkflowStateResponse:
        run_id = legacy_session_id_to_run_id(session_id)
        dynamic_bundle = await self._workflow_run_service.cancel_run(
            run_id,
            CancelWorkflowRunRequest(reason=reason),
        )
        dynamic_response = await self._workflow_run_service.build_run_response(dynamic_bundle.run.id)
        return dynamic_run_to_legacy_session_response(dynamic_response)

    def build_workflow_response(self, response: WorkflowStateResponse) -> WorkflowStateResponse:
        return response

    def _ensure_media_workflow(self, workflow_id: str, session_id: str) -> None:
        if workflow_id != DEFAULT_MEDIA_WORKFLOW_ID:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' was not found.",
            )
