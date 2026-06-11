import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent_client import AgentClient
from app.config import settings
from app.models import (
    ApproveStepRequest,
    ApproveWorkflowNodeRequest,
    CancelWorkflowRequest,
    CancelWorkflowRunRequest,
    CreateAgentRequest,
    CreateSessionRequest,
    CreateWorkflowRequest,
    CreateWorkflowRunRequest,
    CurrentStage,
    DynamicWorkflowProgress,
    FrontendCard,
    RecentSessionsResponse,
    RejectStepRequest,
    RejectWorkflowNodeRequest,
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
    WorkflowBundleResponse,
    WorkflowBundleListResponse,
    WorkflowRunStateResponse,
    UpdateAgentRequest,
    UpdateWorkflowRequest,
)
from app.repositories import InMemoryDynamicRepository
from app.repositories.base import BaseDynamicRepository
from app.repositories.postgres_repository import PostgresDynamicRepository
from app.seed.media_workflow import DEFAULT_MEDIA_WORKFLOW_ID, MEDIA_AGENT_IDS, seed_media_workflow
from app.services.agent_registry_service import AgentRegistryService
from app.services.dag_service import DagService
from app.services.workflow_definition_service import WorkflowDefinitionService
from app.services.workflow_run_service import WorkflowRunService
from app.websocket_manager import WebSocketManager
from app.workflow_engine import WorkflowEngine


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("app.config").info(
        "DAISYNOVA_API_TOKEN configured: %s",
        "yes" if bool(settings.daisynova_api_token) else "no",
    )
    logging.getLogger("app.config").info(
        "ALLOW_AGENT_MOCK_FALLBACK enabled: %s",
        "yes" if settings.allow_agent_mock_fallback else "no",
    )


def validate_runtime_configuration() -> None:
    enabled_agents = [
        agent.name
        for agent in (
            settings.atlas,
            settings.audit,
            settings.media_planner,
            settings.geo_fence,
            settings.meta,
        )
        if agent.enabled
    ]
    if enabled_agents and not settings.daisynova_api_token:
        if settings.allow_agent_mock_fallback:
            logging.getLogger("app.config").warning(
                "DaisyNova API token is missing, but startup is continuing because "
                "ALLOW_AGENT_MOCK_FALLBACK=true."
            )
            return
        raise RuntimeError("DaisyNova API token is missing.")


def create_dynamic_repository() -> BaseDynamicRepository:
    backend = settings.storage_backend.lower()
    if backend == "memory":
        return InMemoryDynamicRepository()
    if backend == "postgres":
        if not settings.database_url:
            raise ValueError("DATABASE_URL must be set when STORAGE_BACKEND=postgres.")
        return PostgresDynamicRepository(settings.database_url)
    raise ValueError("STORAGE_BACKEND must be either 'memory' or 'postgres'.")


def create_app(
    repository=None,
    agent_client: AgentClient | None = None,
) -> FastAPI:
    configure_logging()
    validate_runtime_configuration()
    dynamic_repository = create_dynamic_repository()
    agent_client = agent_client or AgentClient()
    websocket_manager = WebSocketManager()
    dag_service = DagService()
    agent_registry_service = AgentRegistryService(dynamic_repository)
    workflow_definition_service = WorkflowDefinitionService(dynamic_repository, dag_service)
    workflow_run_service = WorkflowRunService(
        repository=dynamic_repository,
        agent_client=agent_client,
        dag_service=dag_service,
        websocket_manager=websocket_manager,
    )
    workflow_engine = WorkflowEngine(workflow_run_service=workflow_run_service)
    seed_lock = None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await dynamic_repository.initialize()
        await seed_media_workflow(dynamic_repository)
        try:
            yield
        finally:
            await dynamic_repository.close()

    async def ensure_dynamic_seeded() -> None:
        nonlocal seed_lock
        if seed_lock is None:
            import asyncio

            seed_lock = asyncio.Lock()
        async with seed_lock:
            await seed_media_workflow(dynamic_repository)

    app = FastAPI(
        title="Multi-Agent Workflow Orchestration API",
        version="1.2.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health", "description": "Service health and readiness endpoints."},
            {"name": "Agents", "description": "Register reusable external APIs as workflow agents."},
            {"name": "Workflows", "description": "Create and manage DAG workflow definitions."},
            {"name": "Workflow Runs", "description": "Execute workflow definitions and manage node approvals."},
        ],
    )
    app.state.repository = dynamic_repository
    app.state.agent_client = agent_client
    app.state.workflow_engine = workflow_engine
    app.state.dynamic_repository = dynamic_repository
    app.state.agent_registry_service = agent_registry_service
    app.state.workflow_definition_service = workflow_definition_service
    app.state.workflow_run_service = workflow_run_service
    app.state.websocket_manager = websocket_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Health"], summary="Health check", description="Returns basic API health status.")
    async def healthcheck() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get(
        "/agents",
        tags=["Agents"],
        summary="List registered agents",
        description="List reusable external API agents available for workflow definitions.",
        responses={
            200: {
                "description": "Registered agents",
                "content": {
                    "application/json": {
                        "example": {
                            "agents": [
                                {
                                    "id": "agent_atlas",
                                    "name": "Atlas Agent",
                                    "description": "Strategic brand intelligence analysis",
                                    "endpoint_url": "https://aiagents.daisynova.com/api/agents/39/run",
                                    "method": "POST",
                                    "headers_json": {
                                        "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                                        "Content-Type": "application/json",
                                    },
                                    "payload_template_json": {
                                        "task": "{{task}}",
                                        "session_id": "{{agent_session_id}}",
                                        "wait": True,
                                    },
                                    "response_mapping_json": {"content": "$.content"},
                                    "auth_type": "bearer",
                                    "enabled": True,
                                    "created_at": "2026-06-09T12:00:00Z",
                                    "updated_at": "2026-06-09T12:00:00Z",
                                    "step_id": "atlas",
                                    "agent_id": 39,
                                    "transport": "run",
                                    "endpoint": "https://aiagents.daisynova.com/api/agents/39/run",
                                }
                            ]
                        }
                    }
                },
            }
        },
    )
    async def list_agents() -> dict[str, list[dict[str, Any]]]:
        await ensure_dynamic_seeded()
        seeded_reverse = {agent_id: step_id for step_id, agent_id in MEDIA_AGENT_IDS.items()}
        agents = await agent_registry_service.list_agents()
        return {
            "agents": [
                {
                    **agent.model_dump(),
                    "step_id": seeded_reverse.get(agent.id),
                    "agent_id": settings.atlas.agent_id if agent.id == MEDIA_AGENT_IDS["atlas"] else
                    settings.audit.agent_id if agent.id == MEDIA_AGENT_IDS["audit"] else
                    settings.media_planner.agent_id if agent.id == MEDIA_AGENT_IDS["media_planner"] else
                    settings.geo_fence.agent_id if agent.id == MEDIA_AGENT_IDS["geo_fence"] else
                    settings.meta.agent_id if agent.id == MEDIA_AGENT_IDS["meta"] else None,
                    "transport": "run",
                    "endpoint": agent.endpoint_url,
                }
                for agent in agents
            ]
        }

    @app.post(
        "/agents",
        tags=["Agents"],
        summary="Register reusable external API",
        description="Register a reusable external API configuration that can be used by workflow nodes.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "daisynovaAgent": {
                                "summary": "Register DaisyNova-style agent",
                                "value": {
                                    "name": "Meta Ads Agent",
                                    "description": "Creates Meta campaign plan",
                                    "endpoint_url": "https://aiagents.daisynova.com/api/agents/70/run",
                                    "method": "POST",
                                    "auth_type": "bearer",
                                    "headers": {
                                        "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                                        "Content-Type": "application/json",
                                    },
                                    "payload_template": {
                                        "task": "{{task}}",
                                        "session_id": "{{agent_session_id}}",
                                        "wait": True,
                                    },
                                    "response_mapping": {"content": "$.content"},
                                    "enabled": True,
                                },
                            }
                        }
                    }
                }
            }
        },
    )
    async def create_agent(request: CreateAgentRequest) -> dict[str, Any]:
        await ensure_dynamic_seeded()
        agent = await agent_registry_service.create_agent(request)
        return {"agent": agent.model_dump()}

    @app.get(
        "/agents/{agent_id}",
        tags=["Agents"],
        summary="Get registered agent",
        description="Fetch one reusable external API agent configuration.",
    )
    async def get_agent(agent_id: str) -> dict[str, Any]:
        await ensure_dynamic_seeded()
        agent = await agent_registry_service.get_agent(agent_id)
        return {"agent": agent.model_dump()}

    @app.patch(
        "/agents/{agent_id}",
        tags=["Agents"],
        summary="Update registered agent",
        description="Update a reusable external API agent configuration.",
    )
    async def update_agent(agent_id: str, request: UpdateAgentRequest) -> dict[str, Any]:
        await ensure_dynamic_seeded()
        agent = await agent_registry_service.update_agent(agent_id, request)
        return {"agent": agent.model_dump()}

    @app.delete(
        "/agents/{agent_id}",
        tags=["Agents"],
        status_code=204,
        summary="Delete registered agent",
        description="Delete a reusable external API agent configuration.",
    )
    async def delete_agent(agent_id: str) -> None:
        await ensure_dynamic_seeded()
        await agent_registry_service.delete_agent(agent_id)

    @app.post(
        "/workflows",
        response_model=WorkflowBundleResponse,
        tags=["Workflows"],
        summary="Create DAG workflow definition",
        description="Create a workflow definition as a directed acyclic graph of nodes and edges.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "mediaWorkflow": {
                                "summary": "Media campaign workflow",
                                "value": {
                                    "name": "Media Campaign Workflow",
                                    "description": "Atlas + Audit, then Media Planner, then Geo + Meta",
                                    "nodes": [
                                        {
                                            "node_key": "atlas",
                                            "agent_id": "agent_atlas",
                                            "display_name": "Atlas Agent",
                                            "approval_required": True,
                                            "input_template": {
                                                "task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"
                                            },
                                            "position": {"x": 100, "y": 100},
                                        },
                                        {
                                            "node_key": "audit",
                                            "agent_id": "agent_audit",
                                            "display_name": "Audit Agent",
                                            "approval_required": True,
                                            "input_template": {
                                                "task": "Perform a detailed brand audit for this URL: {{initial_input.url}}"
                                            },
                                            "position": {"x": 100, "y": 300},
                                        },
                                        {
                                            "node_key": "media_planner",
                                            "agent_id": "agent_media_planner",
                                            "display_name": "Media Planner",
                                            "approval_required": True,
                                            "input_template": {"task": "Create a media plan using this input: {{mapped_input}}"},
                                            "position": {"x": 400, "y": 200},
                                        },
                                    ],
                                    "edges": [
                                        {
                                            "source_node_key": "atlas",
                                            "target_node_key": "media_planner",
                                            "mapping": {"brand_intelligence": "$.approved_output"},
                                        },
                                        {
                                            "source_node_key": "audit",
                                            "target_node_key": "media_planner",
                                            "mapping": {"audit_findings": "$.approved_output"},
                                        },
                                    ],
                                },
                            }
                        }
                    }
                }
            }
        },
    )
    async def create_workflow(request: CreateWorkflowRequest) -> WorkflowBundleResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_definition_service.create_workflow(request)
        return WorkflowBundleResponse(
            workflow=bundle.workflow,
            nodes=bundle.nodes,
            edges=bundle.edges,
        )

    @app.get(
        "/workflows",
        response_model=WorkflowBundleListResponse,
        tags=["Workflows"],
        summary="List workflow definitions",
        description="List workflow DAG definitions available for execution.",
        responses={
            200: {
                "description": "Workflow definitions",
                "content": {
                    "application/json": {
                        "example": {
                            "workflows": [
                                {
                                    "workflow": {
                                        "id": "workflow_media_campaign",
                                        "name": "Media Campaign Workflow",
                                        "description": "Atlas + Audit, then Media Planner, then Geo + Meta",
                                        "version": 1,
                                        "enabled": True,
                                        "created_at": "2026-06-09T12:05:00Z",
                                        "updated_at": "2026-06-09T12:05:00Z",
                                    },
                                    "nodes": [
                                        {
                                            "id": "node_atlas",
                                            "workflow_id": "workflow_media_campaign",
                                            "node_key": "atlas",
                                            "agent_id": "agent_atlas",
                                            "display_name": "Atlas Agent",
                                            "approval_required": True,
                                            "input_template_json": {
                                                "task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"
                                            },
                                            "position_json": {"x": 100, "y": 100},
                                            "created_at": "2026-06-09T12:05:00Z",
                                            "updated_at": "2026-06-09T12:05:00Z",
                                        }
                                    ],
                                    "edges": [
                                        {
                                            "id": "edge_atlas_media",
                                            "workflow_id": "workflow_media_campaign",
                                            "source_node_key": "atlas",
                                            "target_node_key": "media_planner",
                                            "mapping_json": {"brand_intelligence": "$.approved_output"},
                                            "created_at": "2026-06-09T12:05:00Z",
                                            "updated_at": "2026-06-09T12:05:00Z",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            }
        },
    )
    async def list_workflows() -> WorkflowBundleListResponse:
        await ensure_dynamic_seeded()
        bundles = await workflow_definition_service.list_workflows()
        return WorkflowBundleListResponse(
            workflows=[
                WorkflowBundleResponse(workflow=bundle.workflow, nodes=bundle.nodes, edges=bundle.edges)
                for bundle in bundles
            ]
        )

    @app.get(
        "/workflows/{workflow_id}",
        response_model=WorkflowBundleResponse,
        tags=["Workflows"],
        summary="Get workflow definition",
        description="Fetch one DAG workflow definition.",
    )
    async def get_workflow(workflow_id: str) -> WorkflowBundleResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_definition_service.get_workflow(workflow_id)
        return WorkflowBundleResponse(workflow=bundle.workflow, nodes=bundle.nodes, edges=bundle.edges)

    @app.patch(
        "/workflows/{workflow_id}",
        response_model=WorkflowBundleResponse,
        tags=["Workflows"],
        summary="Update workflow definition",
        description="Update a DAG workflow definition.",
    )
    async def update_workflow(workflow_id: str, request: UpdateWorkflowRequest) -> WorkflowBundleResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_definition_service.update_workflow(workflow_id, request)
        return WorkflowBundleResponse(workflow=bundle.workflow, nodes=bundle.nodes, edges=bundle.edges)

    @app.delete(
        "/workflows/{workflow_id}",
        tags=["Workflows"],
        status_code=204,
        summary="Delete workflow definition",
        description="Delete a DAG workflow definition.",
    )
    async def delete_workflow(workflow_id: str) -> None:
        await ensure_dynamic_seeded()
        await workflow_definition_service.delete_workflow(workflow_id)

    @app.post(
        "/workflow-runs",
        response_model=WorkflowRunStateResponse,
        status_code=201,
        tags=["Workflow Runs"],
        summary="Execute workflow definition",
        description="Start a new workflow run from a workflow definition.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "startMediaRun": {
                                "summary": "Start seeded media workflow",
                                "value": {
                                    "workflow_id": "workflow_media_campaign",
                                    "input": {"url": "https://citimedia.in/"},
                                },
                            }
                        }
                    }
                }
            }
        },
    )
    async def create_workflow_run(request: CreateWorkflowRunRequest) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_run_service.create_run(request)
        return await workflow_run_service.build_run_response(bundle.run.id)

    @app.get(
        "/workflow-runs",
        tags=["Workflow Runs"],
        summary="List workflow runs",
        description="List workflow executions that have been started.",
    )
    async def list_workflow_runs() -> dict[str, list[dict[str, Any]]]:
        await ensure_dynamic_seeded()
        runs = await workflow_run_service.list_runs()
        return {"runs": [run.run.model_dump() for run in runs]}

    @app.get(
        "/workflow-runs/{run_id}",
        response_model=WorkflowRunStateResponse,
        tags=["Workflow Runs"],
        summary="Get workflow run state",
        description="Get the current execution state, graph, cards, and node runs for a workflow run.",
        responses={
            200: {
                "description": "Workflow run state",
                "content": {
                    "application/json": {
                        "example": {
                            "run": {
                                "id": "run_123",
                                "workflow_id": "workflow_media_campaign",
                                "status": "WAITING_FOR_APPROVAL",
                                "initial_input_json": {"url": "https://citimedia.in/"},
                                "created_at": "2026-06-09T12:10:00Z",
                                "updated_at": "2026-06-09T12:11:00Z",
                            },
                            "current_stage": "INITIAL_ANALYSIS",
                            "progress": {
                                "total_nodes": 5,
                                "completed_nodes": 0,
                                "waiting_for_approval_nodes": ["atlas", "audit"],
                                "running_nodes": [],
                                "failed_nodes": [],
                            },
                            "frontend_cards": [
                                {
                                    "node_key": "atlas",
                                    "title": "Atlas Agent",
                                    "status": "WAITING_FOR_APPROVAL",
                                    "summary": "Brand intelligence output",
                                    "output": {"content": {"summary": "Brand intelligence output"}},
                                    "mapped_input_preview": None,
                                    "available_actions": ["approve", "reject"],
                                }
                            ],
                            "workflow_graph": {
                                "nodes": [
                                    {"id": "atlas", "label": "Atlas Agent", "status": "WAITING_FOR_APPROVAL"},
                                    {"id": "audit", "label": "Audit Agent", "status": "WAITING_FOR_APPROVAL"},
                                ],
                                "edges": [
                                    {"from": "atlas", "to": "media_planner"},
                                    {"from": "audit", "to": "media_planner"},
                                ],
                            },
                            "available_actions": ["cancel"],
                            "node_runs": {
                                "atlas": {
                                    "id": "node_run_1",
                                    "workflow_run_id": "run_123",
                                    "node_key": "atlas",
                                    "agent_id": "agent_atlas",
                                    "status": "WAITING_FOR_APPROVAL",
                                    "input_task": "Analyze this brand URL for strategic brand intelligence: https://citimedia.in/",
                                    "input_payload_json": {
                                        "task": "Analyze this brand URL for strategic brand intelligence: https://citimedia.in/"
                                    },
                                    "mapped_input_preview": None,
                                    "raw_output_json": {"content": {"summary": "Brand intelligence output"}},
                                    "approved_output_json": None,
                                    "user_feedback_history_json": [],
                                    "rejection_reason": None,
                                    "revision_count": 0,
                                    "error": None,
                                    "agent_session_id": None,
                                    "created_at": "2026-06-09T12:10:00Z",
                                    "updated_at": "2026-06-09T12:11:00Z",
                                }
                            },
                        }
                    }
                },
            }
        },
    )
    async def get_workflow_run(run_id: str) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        return await workflow_run_service.build_run_response(run_id)

    @app.post(
        "/workflow-runs/{run_id}/nodes/{node_key}/approve",
        response_model=WorkflowRunStateResponse,
        tags=["Workflow Runs"],
        summary="Approve node output",
        description="Accept node output and unlock downstream nodes when dependencies are satisfied.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "approveNode": {
                                "summary": "Approve current node output",
                                "value": {},
                            }
                        }
                    }
                }
            }
        },
    )
    async def approve_workflow_node(
        run_id: str,
        node_key: str,
        request: ApproveWorkflowNodeRequest = Body(default_factory=ApproveWorkflowNodeRequest),
    ) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_run_service.approve_node(run_id, node_key, request)
        return await workflow_run_service.build_run_response(bundle.run.id)

    @app.post(
        "/workflow-runs/{run_id}/nodes/{node_key}/reject",
        response_model=WorkflowRunStateResponse,
        tags=["Workflow Runs"],
        summary="Reject and regenerate node output",
        description="Reject the current node output and regenerate the same node without advancing downstream.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "rejectNode": {
                                "summary": "Reject and request regeneration",
                                "value": {"reason": "Please make this more detailed"},
                            }
                        }
                    }
                }
            }
        },
    )
    async def reject_workflow_node(
        run_id: str,
        node_key: str,
        request: RejectWorkflowNodeRequest,
    ) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_run_service.reject_node(run_id, node_key, request.reason)
        return await workflow_run_service.build_run_response(bundle.run.id)

    @app.post(
        "/workflow-runs/{run_id}/nodes/{node_key}/retry",
        response_model=WorkflowRunStateResponse,
        tags=["Workflow Runs"],
        summary="Retry failed node",
        description="Retry a previously failed node using its original rendered task.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "retryNode": {
                                "summary": "Retry failed node",
                                "value": {},
                            }
                        }
                    }
                }
            }
        },
    )
    async def retry_workflow_node(run_id: str, node_key: str) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_run_service.retry_node(run_id, node_key)
        return await workflow_run_service.build_run_response(bundle.run.id)

    @app.post(
        "/workflow-runs/{run_id}/cancel",
        response_model=WorkflowRunStateResponse,
        tags=["Workflow Runs"],
        summary="Cancel workflow run",
        description="Cancel an active workflow run and prevent any further node execution.",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "cancelRun": {
                                "summary": "Cancel workflow run",
                                "value": {"reason": "User cancelled workflow"},
                            }
                        }
                    }
                }
            }
        },
    )
    async def cancel_workflow_run(run_id: str, request: CancelWorkflowRunRequest) -> WorkflowRunStateResponse:
        await ensure_dynamic_seeded()
        bundle = await workflow_run_service.cancel_run(run_id, request)
        return await workflow_run_service.build_run_response(bundle.run.id)

    @app.post(
        "/sessions",
        response_model=WorkflowStateResponse,
        status_code=201,
        include_in_schema=False,
        summary="Create a workflow session",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "default": {
                                "summary": "Create session",
                                "value": {"url": "https://example.com", "user_id": "user_123"},
                            }
                        }
                    }
                }
            }
        },
    )
    async def create_session(request: CreateSessionRequest) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.create_session(request)

    @app.get(
        "/sessions/recent",
        response_model=RecentSessionsResponse,
        include_in_schema=False,
        summary="List recent workflow sessions",
    )
    async def list_recent_sessions(limit: int = 6) -> RecentSessionsResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        safe_limit = min(max(limit, 1), 20)
        return await workflow_engine.list_recent_sessions(limit=safe_limit)

    @app.get(
        "/sessions/{session_id}",
        response_model=WorkflowStateResponse,
        include_in_schema=False,
        summary="Get workflow session state",
    )
    async def get_session(session_id: str) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.get_session(session_id)

    @app.post(
        "/sessions/{session_id}/steps/{step_id}/approve",
        response_model=WorkflowStateResponse,
        include_in_schema=False,
        summary="Approve a workflow step",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "default": {
                                "summary": "Approve step",
                                "value": {},
                            }
                        }
                    }
                }
            }
        },
    )
    async def approve_step(
        session_id: str,
        step_id: StepId,
        request: ApproveStepRequest = Body(default_factory=ApproveStepRequest),
    ) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.approve_step(
            session_id,
            step_id=step_id,
            approved_output=request.approved_output,
        )

    @app.post(
        "/sessions/{session_id}/steps/{step_id}/reject",
        response_model=WorkflowStateResponse,
        include_in_schema=False,
        summary="Reject a workflow step",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "default": {
                                "summary": "Reject step",
                                "value": {"reason": "User rejected this output"},
                            }
                        }
                    }
                }
            }
        },
    )
    async def reject_step(
        session_id: str,
        step_id: StepId,
        request: RejectStepRequest,
    ) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.reject_step(session_id, step_id=step_id, reason=request.reason)

    @app.post(
        "/sessions/{session_id}/steps/{step_id}/retry",
        response_model=WorkflowStateResponse,
        include_in_schema=False,
        summary="Retry a failed workflow step",
    )
    async def retry_step(
        session_id: str,
        step_id: StepId,
    ) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.retry_step(session_id, step_id=step_id)

    @app.post(
        "/sessions/{session_id}/cancel",
        response_model=WorkflowStateResponse,
        include_in_schema=False,
        summary="Cancel a workflow session",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            "default": {
                                "summary": "Cancel workflow",
                                "value": {"reason": "User cancelled workflow"},
                            }
                        }
                    }
                }
            }
        },
    )
    async def cancel_workflow(
        session_id: str,
        request: CancelWorkflowRequest,
    ) -> WorkflowStateResponse:
        # Legacy compatibility endpoint. Hidden from Swagger. Use /workflow-runs for new integrations.
        await ensure_dynamic_seeded()
        return await workflow_engine.cancel_workflow(session_id, reason=request.reason)

    @app.websocket("/ws/sessions/{session_id}")
    async def session_websocket(session_id: str, websocket: WebSocket) -> None:
        await websocket_manager.connect(session_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_manager.disconnect(session_id, websocket)
        except Exception:
            websocket_manager.disconnect(session_id, websocket)

    @app.websocket("/ws/workflow-runs/{run_id}")
    async def workflow_run_websocket(run_id: str, websocket: WebSocket) -> None:
        await websocket_manager.connect(run_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_manager.disconnect(run_id, websocket)
        except Exception:
            websocket_manager.disconnect(run_id, websocket)

    return app


app = create_app()
