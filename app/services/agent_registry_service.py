from __future__ import annotations

from fastapi import HTTPException, status

from app.models import (
    AgentDefinition,
    CreateAgentRequest,
    UpdateAgentRequest,
    new_id,
    utc_now,
)
from app.repositories.base import BaseDynamicRepository, DynamicEntityNotFoundError


class AgentRegistryService:
    def __init__(self, repository: BaseDynamicRepository) -> None:
        self._repository = repository

    async def create_agent(self, request: CreateAgentRequest) -> AgentDefinition:
        now = utc_now()
        agent = AgentDefinition(
            id=new_id("agent"),
            name=request.name,
            description=request.description,
            endpoint_url=request.endpoint_url,
            method=request.method,
            headers_json=request.headers,
            payload_template_json=request.payload_template,
            response_mapping_json=request.response_mapping,
            auth_type=request.auth_type,
            enabled=request.enabled,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_agent(agent)

    async def list_agents(self) -> list[AgentDefinition]:
        return await self._repository.list_agents()

    async def get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return await self._repository.get_agent(agent_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.") from exc

    async def update_agent(self, agent_id: str, request: UpdateAgentRequest) -> AgentDefinition:
        async def updater(agent: AgentDefinition) -> AgentDefinition:
            if request.name is not None:
                agent.name = request.name
            if request.description is not None:
                agent.description = request.description
            if request.endpoint_url is not None:
                agent.endpoint_url = request.endpoint_url
            if request.method is not None:
                agent.method = request.method
            if request.headers is not None:
                agent.headers_json = request.headers
            if request.payload_template is not None:
                agent.payload_template_json = request.payload_template
            if request.response_mapping is not None:
                agent.response_mapping_json = request.response_mapping
            if request.auth_type is not None:
                agent.auth_type = request.auth_type
            if request.enabled is not None:
                agent.enabled = request.enabled
            return agent

        try:
            return await self._repository.update_agent(agent_id, updater)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.") from exc

    async def delete_agent(self, agent_id: str) -> None:
        try:
            await self._repository.delete_agent(agent_id)
        except DynamicEntityNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.") from exc
