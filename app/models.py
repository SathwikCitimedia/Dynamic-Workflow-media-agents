from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CurrentStage(str, Enum):
    INITIAL_ANALYSIS = "INITIAL_ANALYSIS"
    MEDIA_PLANNING = "MEDIA_PLANNING"
    ACTIVATION = "ACTIVATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


StepId = Literal["atlas", "audit", "media_planner", "geo_fence", "meta"]
StepAction = Literal["approve", "reject"]


class AgentResponse(BaseModel):
    content: Any
    text: str | None = None
    raw: Any


class WorkflowStep(BaseModel):
    session_id: str
    step_id: StepId
    status: StepStatus
    agent_session_id: str | None = None
    input_task: str | None = None
    mapped_input_preview: Any | None = None
    raw_output: Any | None = None
    approved_output: Any | None = None
    user_feedback_history: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    revision_count: int = 0
    error: str | None = None
    available_actions: list[StepAction] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowSession(BaseModel):
    session_id: str
    url: HttpUrl
    user_id: str
    steps: dict[StepId, WorkflowStep]
    workflow_status: WorkflowStatus = WorkflowStatus.RUNNING
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class CreateSessionRequest(BaseModel):
    url: HttpUrl
    user_id: str | None = None

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("user_id cannot be empty.")
        return stripped


class ApproveStepRequest(BaseModel):
    approved_output: Any | None = None


class RejectStepRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason cannot be empty.")
        return stripped


class CancelWorkflowRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason cannot be empty.")
        return stripped


class WorkflowStateResponse(BaseModel):
    session: WorkflowSession
    current_stage: CurrentStage
    progress: "WorkflowProgress"
    frontend_cards: list["FrontendCard"]
    workflow_graph: "WorkflowGraph"


class RecentSessionSummary(BaseModel):
    session_id: str
    url: HttpUrl
    workflow_status: WorkflowStatus
    current_stage: CurrentStage
    updated_at: datetime
    progress: "WorkflowProgress"


class RecentSessionsResponse(BaseModel):
    sessions: list[RecentSessionSummary]


class AgentSummary(BaseModel):
    name: str
    step_id: StepId
    agent_id: int | None
    transport: str
    enabled: bool
    endpoint: str | None


class AgentsResponse(BaseModel):
    agents: list[AgentSummary]


class WorkflowProgress(BaseModel):
    total_steps: int
    completed_steps: int
    waiting_for_approval_steps: list[StepId]
    running_steps: list[StepId]
    failed_steps: list[StepId]


class FrontendCard(BaseModel):
    step_id: StepId
    title: str
    status: StepStatus
    summary: str
    output: Any
    mapped_input_preview: Any | None = None
    available_actions: list[StepAction]


class WorkflowGraphNode(BaseModel):
    id: StepId
    label: str
    status: StepStatus


class WorkflowGraphEdge(BaseModel):
    from_: StepId = Field(alias="from")
    to: StepId


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowGraphNode]
    edges: list[WorkflowGraphEdge]


def build_default_steps(session_id: str) -> dict[StepId, WorkflowStep]:
    return {
        "atlas": WorkflowStep(
            session_id=session_id,
            step_id="atlas",
            status=StepStatus.PENDING,
        ),
        "audit": WorkflowStep(
            session_id=session_id,
            step_id="audit",
            status=StepStatus.PENDING,
        ),
        "media_planner": WorkflowStep(
            session_id=session_id,
            step_id="media_planner",
            status=StepStatus.PENDING,
        ),
        "geo_fence": WorkflowStep(
            session_id=session_id,
            step_id="geo_fence",
            status=StepStatus.PENDING,
        ),
        "meta": WorkflowStep(
            session_id=session_id,
            step_id="meta",
            status=StepStatus.PENDING,
        ),
    }


def new_session_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def derive_workflow_status(steps: dict[StepId, WorkflowStep]) -> WorkflowStatus:
    statuses = [step.status for step in steps.values()]
    if any(status in {StepStatus.REJECTED, StepStatus.CANCELLED} for status in statuses):
        return WorkflowStatus.CANCELLED
    if any(status == StepStatus.FAILED for status in statuses):
        return WorkflowStatus.FAILED
    if any(status == StepStatus.WAITING_FOR_APPROVAL for status in statuses):
        return WorkflowStatus.WAITING_FOR_APPROVAL

    final_statuses = {StepStatus.APPROVED, StepStatus.SKIPPED}
    if all(status in final_statuses for status in statuses):
        return WorkflowStatus.COMPLETED

    return WorkflowStatus.RUNNING


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"


class DynamicNodeAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    RETRY = "retry"


class AgentDefinition(BaseModel):
    id: str
    name: str
    description: str | None = None
    endpoint_url: str
    method: str = "POST"
    headers_json: dict[str, Any] = Field(default_factory=dict)
    payload_template_json: dict[str, Any] = Field(default_factory=dict)
    response_mapping_json: dict[str, Any] = Field(default_factory=dict)
    auth_type: AuthType = AuthType.NONE
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: int = 1
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowNodeDefinition(BaseModel):
    id: str
    workflow_id: str
    node_key: str
    agent_id: str
    display_name: str
    approval_required: bool = True
    input_template_json: dict[str, Any] = Field(default_factory=dict)
    position_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowEdgeDefinition(BaseModel):
    id: str
    workflow_id: str
    source_node_key: str
    target_node_key: str
    mapping_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowBundle(BaseModel):
    workflow: WorkflowDefinition
    nodes: list[WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]


class WorkflowRun(BaseModel):
    id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    initial_input_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowNodeRun(BaseModel):
    id: str
    workflow_run_id: str
    node_key: str
    agent_id: str
    status: StepStatus = StepStatus.PENDING
    input_task: str | None = None
    input_payload_json: dict[str, Any] | None = None
    mapped_input_preview: Any | None = None
    raw_output_json: Any | None = None
    approved_output_json: Any | None = None
    user_feedback_history_json: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    revision_count: int = 0
    error: str | None = None
    agent_session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: utc_now())
    updated_at: datetime = Field(default_factory=lambda: utc_now())


class WorkflowRunBundle(BaseModel):
    run: WorkflowRun
    node_runs: dict[str, WorkflowNodeRun]


class CreateAgentRequest(BaseModel):
    name: str
    description: str | None = None
    endpoint_url: str
    method: str = "POST"
    headers: dict[str, Any] = Field(default_factory=dict)
    payload_template: dict[str, Any] = Field(default_factory=dict)
    response_mapping: dict[str, Any] = Field(default_factory=dict)
    auth_type: AuthType = AuthType.NONE
    enabled: bool = True


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    method: str | None = None
    headers: dict[str, Any] | None = None
    payload_template: dict[str, Any] | None = None
    response_mapping: dict[str, Any] | None = None
    auth_type: AuthType | None = None
    enabled: bool | None = None


class AgentDefinitionResponse(BaseModel):
    agent: AgentDefinition


class AgentDefinitionListResponse(BaseModel):
    agents: list[AgentDefinition]


class WorkflowNodeCreateRequest(BaseModel):
    node_key: str
    agent_id: str
    display_name: str
    approval_required: bool = True
    input_template: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgeCreateRequest(BaseModel):
    source_node_key: str
    target_node_key: str
    mapping: dict[str, Any] = Field(default_factory=dict)


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str | None = None
    version: int = 1
    enabled: bool = True
    nodes: list[WorkflowNodeCreateRequest] = Field(default_factory=list)
    edges: list[WorkflowEdgeCreateRequest] = Field(default_factory=list)


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    version: int | None = None
    enabled: bool | None = None
    nodes: list[WorkflowNodeCreateRequest] | None = None
    edges: list[WorkflowEdgeCreateRequest] | None = None


class WorkflowBundleResponse(BaseModel):
    workflow: WorkflowDefinition
    nodes: list[WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]


class WorkflowBundleListResponse(BaseModel):
    workflows: list[WorkflowBundleResponse]


class CreateWorkflowRunRequest(BaseModel):
    workflow_id: str
    input: dict[str, Any] = Field(default_factory=dict)


class ApproveWorkflowNodeRequest(BaseModel):
    approved_output: Any | None = None


class RejectWorkflowNodeRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason_dynamic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason cannot be empty.")
        return stripped


class CancelWorkflowRunRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_cancel_reason_dynamic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason cannot be empty.")
        return stripped


class DynamicWorkflowGraphNode(BaseModel):
    id: str
    label: str
    status: StepStatus


class DynamicWorkflowGraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str


class DynamicWorkflowGraph(BaseModel):
    nodes: list[DynamicWorkflowGraphNode]
    edges: list[DynamicWorkflowGraphEdge]


class DynamicFrontendCard(BaseModel):
    node_key: str
    title: str
    status: StepStatus
    summary: str
    output: Any
    mapped_input_preview: Any | None = None
    available_actions: list[str] = Field(default_factory=list)


class DynamicWorkflowProgress(BaseModel):
    total_nodes: int
    completed_nodes: int
    waiting_for_approval_nodes: list[str]
    running_nodes: list[str]
    failed_nodes: list[str]


class WorkflowRunStateResponse(BaseModel):
    run: WorkflowRun
    current_stage: str
    progress: DynamicWorkflowProgress
    frontend_cards: list[DynamicFrontendCard]
    workflow_graph: DynamicWorkflowGraph
    available_actions: list[str]
    node_runs: dict[str, WorkflowNodeRun]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
