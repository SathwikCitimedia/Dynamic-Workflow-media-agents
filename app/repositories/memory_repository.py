from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.models import AgentDefinition, WorkflowBundle, WorkflowNodeRun, WorkflowRunBundle, utc_now
from app.repositories.base import BaseDynamicRepository, DynamicEntityNotFoundError


class InMemoryDynamicRepository(BaseDynamicRepository):
    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        self._workflows: dict[str, WorkflowBundle] = {}
        self._workflow_runs: dict[str, WorkflowRunBundle] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def create_agent(self, agent: AgentDefinition) -> AgentDefinition:
        async with self._global_lock:
            self._agents[agent.id] = agent.model_copy(deep=True)
        return agent.model_copy(deep=True)

    async def list_agents(self) -> list[AgentDefinition]:
        return [agent.model_copy(deep=True) for agent in self._agents.values()]

    async def get_agent(self, agent_id: str) -> AgentDefinition:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise DynamicEntityNotFoundError(agent_id)
        return agent.model_copy(deep=True)

    async def update_agent(
        self,
        agent_id: str,
        updater: Callable[[AgentDefinition], AgentDefinition | Awaitable[AgentDefinition]],
    ) -> AgentDefinition:
        async with self._global_lock:
            current = self._agents.get(agent_id)
            if current is None:
                raise DynamicEntityNotFoundError(agent_id)
            working = current.model_copy(deep=True)
            updated = updater(working)
            if asyncio.iscoroutine(updated):
                updated = await updated
            updated.updated_at = utc_now()
            self._agents[agent_id] = updated.model_copy(deep=True)
            return updated.model_copy(deep=True)

    async def delete_agent(self, agent_id: str) -> None:
        async with self._global_lock:
            if agent_id not in self._agents:
                raise DynamicEntityNotFoundError(agent_id)
            del self._agents[agent_id]

    async def save_workflow_bundle(self, bundle: WorkflowBundle) -> WorkflowBundle:
        async with self._global_lock:
            self._workflows[bundle.workflow.id] = bundle.model_copy(deep=True)
        return bundle.model_copy(deep=True)

    async def list_workflow_bundles(self) -> list[WorkflowBundle]:
        return [bundle.model_copy(deep=True) for bundle in self._workflows.values()]

    async def get_workflow_bundle(self, workflow_id: str) -> WorkflowBundle:
        bundle = self._workflows.get(workflow_id)
        if bundle is None:
            raise DynamicEntityNotFoundError(workflow_id)
        return bundle.model_copy(deep=True)

    async def delete_workflow_bundle(self, workflow_id: str) -> None:
        async with self._global_lock:
            if workflow_id not in self._workflows:
                raise DynamicEntityNotFoundError(workflow_id)
            del self._workflows[workflow_id]

    async def create_workflow_run_bundle(self, bundle: WorkflowRunBundle) -> WorkflowRunBundle:
        async with self._global_lock:
            self._workflow_runs[bundle.run.id] = bundle.model_copy(deep=True)
            self._locks.setdefault(bundle.run.id, asyncio.Lock())
        return bundle.model_copy(deep=True)

    async def list_workflow_run_bundles(self) -> list[WorkflowRunBundle]:
        runs = sorted(self._workflow_runs.values(), key=lambda item: item.run.updated_at, reverse=True)
        return [bundle.model_copy(deep=True) for bundle in runs]

    async def get_workflow_run_bundle(self, run_id: str) -> WorkflowRunBundle:
        bundle = self._workflow_runs.get(run_id)
        if bundle is None:
            raise DynamicEntityNotFoundError(run_id)
        return bundle.model_copy(deep=True)

    async def update_workflow_run_bundle(
        self,
        run_id: str,
        updater: Callable[[WorkflowRunBundle], WorkflowRunBundle | Awaitable[WorkflowRunBundle]],
    ) -> WorkflowRunBundle:
        lock = self._locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            current = self._workflow_runs.get(run_id)
            if current is None:
                raise DynamicEntityNotFoundError(run_id)
            working = current.model_copy(deep=True)
            updated = updater(working)
            if asyncio.iscoroutine(updated):
                updated = await updated
            updated.run.updated_at = utc_now()
            self._workflow_runs[run_id] = updated.model_copy(deep=True)
            return updated.model_copy(deep=True)

    async def get_node_run(self, run_id: str, node_key: str) -> WorkflowNodeRun:
        bundle = await self.get_workflow_run_bundle(run_id)
        node_run = bundle.node_runs.get(node_key)
        if node_run is None:
            raise DynamicEntityNotFoundError(f"{run_id}:{node_key}")
        return node_run.model_copy(deep=True)
