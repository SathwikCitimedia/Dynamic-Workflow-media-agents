from __future__ import annotations

from app.models import (
    AgentDefinition,
    AuthType,
    WorkflowBundle,
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    utc_now,
)
from app.repositories.base import BaseDynamicRepository, DynamicEntityNotFoundError


MEDIA_AGENT_IDS = {
    "atlas": "agent_atlas",
    "audit": "agent_audit",
    "media_planner": "agent_media_planner",
    "geo_fence": "agent_geo_fence",
    "meta": "agent_meta",
}
DEFAULT_MEDIA_WORKFLOW_ID = "workflow_media_campaign"


async def seed_media_workflow(repository: BaseDynamicRepository) -> None:
    now = utc_now()
    agents = [
        AgentDefinition(
            id=MEDIA_AGENT_IDS["atlas"],
            name="Atlas Agent",
            description="Strategic brand intelligence analysis",
            endpoint_url="https://aiagents.daisynova.com/api/agents/39/run",
            method="POST",
            headers_json={
                "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                "Content-Type": "application/json",
            },
            payload_template_json={"task": "{{task}}", "session_id": "{{agent_session_id}}", "wait": True},
            response_mapping_json={"content": "$.content"},
            auth_type=AuthType.BEARER,
            enabled=True,
            created_at=now,
            updated_at=now,
        ),
        AgentDefinition(
            id=MEDIA_AGENT_IDS["audit"],
            name="Audit Agent",
            description="Detailed brand audit analysis",
            endpoint_url="https://aiagents.daisynova.com/api/agents/14/run",
            method="POST",
            headers_json={
                "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                "Content-Type": "application/json",
            },
            payload_template_json={"task": "{{task}}", "session_id": "{{agent_session_id}}", "wait": True},
            response_mapping_json={"content": "$.content"},
            auth_type=AuthType.BEARER,
            enabled=True,
            created_at=now,
            updated_at=now,
        ),
        AgentDefinition(
            id=MEDIA_AGENT_IDS["media_planner"],
            name="Media Planner Agent",
            description="Media planning agent",
            endpoint_url="https://aiagents.daisynova.com/api/agents/43/run",
            method="POST",
            headers_json={
                "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                "Content-Type": "application/json",
            },
            payload_template_json={"task": "{{task}}", "session_id": "{{agent_session_id}}", "wait": True},
            response_mapping_json={"content": "$.content"},
            auth_type=AuthType.BEARER,
            enabled=True,
            created_at=now,
            updated_at=now,
        ),
        AgentDefinition(
            id=MEDIA_AGENT_IDS["geo_fence"],
            name="Geo Fence Agent",
            description="Geo fencing agent",
            endpoint_url="https://aiagents.daisynova.com/api/agents/74/run",
            method="POST",
            headers_json={
                "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                "Content-Type": "application/json",
            },
            payload_template_json={"task": "{{task}}", "session_id": "{{agent_session_id}}", "wait": True},
            response_mapping_json={"content": "$.content"},
            auth_type=AuthType.BEARER,
            enabled=True,
            created_at=now,
            updated_at=now,
        ),
        AgentDefinition(
            id=MEDIA_AGENT_IDS["meta"],
            name="Meta Agent",
            description="Meta ads planning agent",
            endpoint_url="https://aiagents.daisynova.com/api/agents/70/run",
            method="POST",
            headers_json={
                "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
                "Content-Type": "application/json",
            },
            payload_template_json={"task": "{{task}}", "session_id": "{{agent_session_id}}", "wait": True},
            response_mapping_json={"content": "$.content"},
            auth_type=AuthType.BEARER,
            enabled=True,
            created_at=now,
            updated_at=now,
        ),
    ]
    for agent in agents:
        try:
            await repository.get_agent(agent.id)
        except DynamicEntityNotFoundError:
            await repository.create_agent(agent)

    try:
        await repository.get_workflow_bundle(DEFAULT_MEDIA_WORKFLOW_ID)
        return
    except DynamicEntityNotFoundError:
        pass

    workflow = WorkflowDefinition(
        id=DEFAULT_MEDIA_WORKFLOW_ID,
        name="Media Campaign Workflow",
        description="Atlas + Audit, then Media Planner, then Geo + Meta",
        version=1,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    nodes = [
        WorkflowNodeDefinition(
            id="node_atlas",
            workflow_id=workflow.id,
            node_key="atlas",
            agent_id=MEDIA_AGENT_IDS["atlas"],
            display_name="Atlas Agent",
            approval_required=True,
            input_template_json={"task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"},
            position_json={"x": 100, "y": 100},
            created_at=now,
            updated_at=now,
        ),
        WorkflowNodeDefinition(
            id="node_audit",
            workflow_id=workflow.id,
            node_key="audit",
            agent_id=MEDIA_AGENT_IDS["audit"],
            display_name="Audit Agent",
            approval_required=True,
            input_template_json={"task": "Perform a detailed brand audit for this URL: {{initial_input.url}}"},
            position_json={"x": 100, "y": 300},
            created_at=now,
            updated_at=now,
        ),
        WorkflowNodeDefinition(
            id="node_media_planner",
            workflow_id=workflow.id,
            node_key="media_planner",
            agent_id=MEDIA_AGENT_IDS["media_planner"],
            display_name="Media Planner",
            approval_required=True,
            input_template_json={"task": "Create a media plan using this input: {{mapped_input}}"},
            position_json={"x": 400, "y": 200},
            created_at=now,
            updated_at=now,
        ),
        WorkflowNodeDefinition(
            id="node_geo_fence",
            workflow_id=workflow.id,
            node_key="geo_fence",
            agent_id=MEDIA_AGENT_IDS["geo_fence"],
            display_name="Geo Fence Agent",
            approval_required=True,
            input_template_json={"task": "Create a geo fencing strategy using this media plan: {{mapped_input}}"},
            position_json={"x": 700, "y": 100},
            created_at=now,
            updated_at=now,
        ),
        WorkflowNodeDefinition(
            id="node_meta",
            workflow_id=workflow.id,
            node_key="meta",
            agent_id=MEDIA_AGENT_IDS["meta"],
            display_name="Meta Agent",
            approval_required=True,
            input_template_json={"task": "Create a Meta ads campaign using this media plan: {{mapped_input}}"},
            position_json={"x": 700, "y": 300},
            created_at=now,
            updated_at=now,
        ),
    ]
    edges = [
        WorkflowEdgeDefinition(
            id="edge_atlas_media",
            workflow_id=workflow.id,
            source_node_key="atlas",
            target_node_key="media_planner",
            mapping_json={"brand_intelligence": "$.approved_output"},
            created_at=now,
            updated_at=now,
        ),
        WorkflowEdgeDefinition(
            id="edge_audit_media",
            workflow_id=workflow.id,
            source_node_key="audit",
            target_node_key="media_planner",
            mapping_json={"audit_findings": "$.approved_output"},
            created_at=now,
            updated_at=now,
        ),
        WorkflowEdgeDefinition(
            id="edge_media_geo",
            workflow_id=workflow.id,
            source_node_key="media_planner",
            target_node_key="geo_fence",
            mapping_json={"media_plan": "$.approved_output"},
            created_at=now,
            updated_at=now,
        ),
        WorkflowEdgeDefinition(
            id="edge_media_meta",
            workflow_id=workflow.id,
            source_node_key="media_planner",
            target_node_key="meta",
            mapping_json={"media_plan": "$.approved_output"},
            created_at=now,
            updated_at=now,
        ),
    ]
    await repository.save_workflow_bundle(WorkflowBundle(workflow=workflow, nodes=nodes, edges=edges))
