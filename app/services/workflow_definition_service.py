from __future__ import annotations

from fastapi import HTTPException, status

from app.models import (
    CreateWorkflowRequest,
    WorkflowBundle,
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    UpdateWorkflowRequest,
    new_id,
    utc_now,
)
from app.repositories.base import BaseDynamicRepository, DynamicEntityNotFoundError
from app.services.dag_service import DagService


class WorkflowDefinitionService:
    def __init__(self, repository: BaseDynamicRepository, dag_service: DagService) -> None:
        self._repository = repository
        self._dag_service = dag_service

    async def create_workflow(self, request: CreateWorkflowRequest) -> WorkflowBundle:
        now = utc_now()
        workflow = WorkflowDefinition(
            id=new_id("workflow"),
            name=request.name,
            description=request.description,
            version=request.version,
            enabled=request.enabled,
            created_at=now,
            updated_at=now,
        )
        bundle = WorkflowBundle(
            workflow=workflow,
            nodes=[
                WorkflowNodeDefinition(
                    id=new_id("node"),
                    workflow_id=workflow.id,
                    node_key=node.node_key,
                    agent_id=node.agent_id,
                    display_name=node.display_name,
                    approval_required=node.approval_required,
                    input_template_json=node.input_template,
                    position_json=node.position,
                    created_at=now,
                    updated_at=now,
                )
                for node in request.nodes
            ],
            edges=[
                WorkflowEdgeDefinition(
                    id=new_id("edge"),
                    workflow_id=workflow.id,
                    source_node_key=edge.source_node_key,
                    target_node_key=edge.target_node_key,
                    mapping_json=edge.mapping,
                    created_at=now,
                    updated_at=now,
                )
                for edge in request.edges
            ],
        )
        agents = {agent.id: agent for agent in await self._repository.list_agents()}
        self._dag_service.validate(bundle, agents)
        return await self._repository.save_workflow_bundle(bundle)

    async def list_workflows(self) -> list[WorkflowBundle]:
        return await self._repository.list_workflow_bundles()

    async def get_workflow(self, workflow_id: str) -> WorkflowBundle:
        try:
            return await self._repository.get_workflow_bundle(workflow_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.") from exc

    async def update_workflow(self, workflow_id: str, request: UpdateWorkflowRequest) -> WorkflowBundle:
        existing = await self.get_workflow(workflow_id)
        workflow = existing.workflow.model_copy(deep=True)
        if request.name is not None:
            workflow.name = request.name
        if request.description is not None:
            workflow.description = request.description
        if request.version is not None:
            workflow.version = request.version
        if request.enabled is not None:
            workflow.enabled = request.enabled
        workflow.updated_at = utc_now()

        nodes = existing.nodes
        if request.nodes is not None:
            now = utc_now()
            nodes = [
                WorkflowNodeDefinition(
                    id=new_id("node"),
                    workflow_id=workflow.id,
                    node_key=node.node_key,
                    agent_id=node.agent_id,
                    display_name=node.display_name,
                    approval_required=node.approval_required,
                    input_template_json=node.input_template,
                    position_json=node.position,
                    created_at=now,
                    updated_at=now,
                )
                for node in request.nodes
            ]

        edges = existing.edges
        if request.edges is not None:
            now = utc_now()
            edges = [
                WorkflowEdgeDefinition(
                    id=new_id("edge"),
                    workflow_id=workflow.id,
                    source_node_key=edge.source_node_key,
                    target_node_key=edge.target_node_key,
                    mapping_json=edge.mapping,
                    created_at=now,
                    updated_at=now,
                )
                for edge in request.edges
            ]

        bundle = WorkflowBundle(workflow=workflow, nodes=nodes, edges=edges)
        agents = {agent.id: agent for agent in await self._repository.list_agents()}
        self._dag_service.validate(bundle, agents)
        return await self._repository.save_workflow_bundle(bundle)

    async def delete_workflow(self, workflow_id: str) -> None:
        try:
            await self._repository.delete_workflow_bundle(workflow_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.") from exc
