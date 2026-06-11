from __future__ import annotations

from typing import Any

from app.config import settings
from app.models import (
    CurrentStage,
    FrontendCard,
    RecentSessionSummary,
    RecentSessionsResponse,
    StepAction,
    StepId,
    StepStatus,
    WorkflowGraph,
    WorkflowGraphEdge,
    WorkflowGraphNode,
    WorkflowProgress,
    WorkflowSession,
    WorkflowStateResponse,
    WorkflowStatus,
    WorkflowStep,
    WorkflowRunStateResponse,
)


LEGACY_STEP_ORDER: tuple[StepId, ...] = ("atlas", "audit", "media_planner", "geo_fence", "meta")


def legacy_step_id_to_node_key(step_id: StepId) -> str:
    return step_id


def legacy_session_id_to_run_id(session_id: str) -> str:
    return session_id


def dynamic_run_to_legacy_session_response(dynamic_response: WorkflowRunStateResponse) -> WorkflowStateResponse:
    initial_input = dynamic_response.run.initial_input_json
    user_id = initial_input.get("user_id", settings.agent_user_id)
    steps: dict[StepId, WorkflowStep] = {}
    for step_id in LEGACY_STEP_ORDER:
        node_run = dynamic_response.node_runs[step_id]
        steps[step_id] = WorkflowStep(
            session_id=dynamic_response.run.id,
            step_id=step_id,
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
            available_actions=_legacy_actions_for_status(node_run.status),
            updated_at=node_run.updated_at,
        )

    session = WorkflowSession(
        session_id=dynamic_response.run.id,
        url=initial_input["url"],
        user_id=user_id,
        steps=steps,
        workflow_status=_derive_legacy_workflow_status(steps, dynamic_response.run.status),
        updated_at=dynamic_response.run.updated_at,
    )

    current_stage = _derive_legacy_current_stage(session)
    progress = WorkflowProgress(
        total_steps=len(steps),
        completed_steps=sum(1 for step in steps.values() if step.status in {StepStatus.APPROVED, StepStatus.SKIPPED}),
        waiting_for_approval_steps=[step_id for step_id, step in steps.items() if step.status == StepStatus.WAITING_FOR_APPROVAL],
        running_steps=[step_id for step_id, step in steps.items() if step.status == StepStatus.RUNNING],
        failed_steps=[step_id for step_id, step in steps.items() if step.status in {StepStatus.FAILED, StepStatus.CANCELLED}],
    )
    frontend_cards = [
        FrontendCard(
            step_id=card.node_key,
            title=card.title,
            status=card.status,
            summary=card.summary,
            output=card.output,
            mapped_input_preview=card.mapped_input_preview,
            available_actions=[action for action in card.available_actions if action in {"approve", "reject"}],
        )
        for card in dynamic_response.frontend_cards
        if card.node_key in LEGACY_STEP_ORDER
    ]
    workflow_graph = WorkflowGraph(
        nodes=[
            WorkflowGraphNode(id=node.id, label=_legacy_graph_label(node.id, node.label), status=node.status)
            for node in dynamic_response.workflow_graph.nodes
            if node.id in LEGACY_STEP_ORDER
        ],
        edges=[
            WorkflowGraphEdge(**{"from": edge.from_, "to": edge.to})
            for edge in dynamic_response.workflow_graph.edges
            if edge.from_ in LEGACY_STEP_ORDER and edge.to in LEGACY_STEP_ORDER
        ],
    )
    return WorkflowStateResponse(
        session=session,
        current_stage=current_stage,
        progress=progress,
        frontend_cards=frontend_cards,
        workflow_graph=workflow_graph,
    )


def dynamic_recent_runs_to_legacy_recent_sessions(responses: list[WorkflowRunStateResponse]) -> RecentSessionsResponse:
    sessions: list[RecentSessionSummary] = []
    for response in responses:
        legacy = dynamic_run_to_legacy_session_response(response)
        sessions.append(
            RecentSessionSummary(
                session_id=legacy.session.session_id,
                url=legacy.session.url,
                workflow_status=legacy.session.workflow_status,
                current_stage=legacy.current_stage,
                updated_at=legacy.session.updated_at,
                progress=legacy.progress,
            )
        )
    return RecentSessionsResponse(sessions=sessions)


def _derive_legacy_workflow_status(steps: dict[StepId, WorkflowStep], dynamic_status: WorkflowStatus) -> WorkflowStatus:
    if dynamic_status == WorkflowStatus.CANCELLED:
        return WorkflowStatus.CANCELLED
    statuses = [step.status for step in steps.values()]
    if all(status in {StepStatus.APPROVED, StepStatus.SKIPPED} for status in statuses):
        return WorkflowStatus.COMPLETED
    if any(status == StepStatus.WAITING_FOR_APPROVAL for status in statuses):
        return WorkflowStatus.WAITING_FOR_APPROVAL
    if any(status == StepStatus.RUNNING for status in statuses):
        return WorkflowStatus.RUNNING
    if any(status == StepStatus.FAILED for status in statuses):
        return WorkflowStatus.FAILED
    return dynamic_status


def _derive_legacy_current_stage(session: WorkflowSession) -> CurrentStage:
    if session.workflow_status == WorkflowStatus.COMPLETED:
        return CurrentStage.COMPLETED
    if session.workflow_status == WorkflowStatus.CANCELLED:
        return CurrentStage.CANCELLED
    if session.workflow_status == WorkflowStatus.FAILED:
        return CurrentStage.FAILED
    media_status = session.steps["media_planner"].status
    activation_statuses = [session.steps["geo_fence"].status, session.steps["meta"].status]
    if media_status in {StepStatus.APPROVED, StepStatus.SKIPPED} or any(
        status not in {StepStatus.PENDING, StepStatus.SKIPPED} for status in activation_statuses
    ):
        return CurrentStage.ACTIVATION
    if media_status != StepStatus.PENDING:
        return CurrentStage.MEDIA_PLANNING
    return CurrentStage.INITIAL_ANALYSIS


def _legacy_actions_for_status(status: StepStatus) -> list[StepAction]:
    if status == StepStatus.WAITING_FOR_APPROVAL:
        return ["approve", "reject"]
    return []


def _legacy_graph_label(node_id: str, fallback: str) -> str:
    mapping = {
        "atlas": "Atlas",
        "audit": "Audit",
        "media_planner": "Media Planner",
        "geo_fence": "Geo Fence",
        "meta": "Meta",
    }
    return mapping.get(node_id, fallback)
