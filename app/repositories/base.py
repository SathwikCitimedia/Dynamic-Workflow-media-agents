from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.models import (
    AgentDefinition,
    WorkflowBundle,
    WorkflowNodeRun,
    WorkflowRunBundle,
)


class DynamicEntityNotFoundError(KeyError):
    """Raised when a dynamic workflow entity is missing."""


class BaseDynamicRepository(ABC):
    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @abstractmethod
    async def create_agent(self, agent: AgentDefinition) -> AgentDefinition:
        raise NotImplementedError

    @abstractmethod
    async def list_agents(self) -> list[AgentDefinition]:
        raise NotImplementedError

    @abstractmethod
    async def get_agent(self, agent_id: str) -> AgentDefinition:
        raise NotImplementedError

    @abstractmethod
    async def update_agent(
        self,
        agent_id: str,
        updater: Callable[[AgentDefinition], AgentDefinition | Awaitable[AgentDefinition]],
    ) -> AgentDefinition:
        raise NotImplementedError

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_workflow_bundle(self, bundle: WorkflowBundle) -> WorkflowBundle:
        raise NotImplementedError

    @abstractmethod
    async def list_workflow_bundles(self) -> list[WorkflowBundle]:
        raise NotImplementedError

    @abstractmethod
    async def get_workflow_bundle(self, workflow_id: str) -> WorkflowBundle:
        raise NotImplementedError

    @abstractmethod
    async def delete_workflow_bundle(self, workflow_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def create_workflow_run_bundle(self, bundle: WorkflowRunBundle) -> WorkflowRunBundle:
        raise NotImplementedError

    @abstractmethod
    async def list_workflow_run_bundles(self) -> list[WorkflowRunBundle]:
        raise NotImplementedError

    @abstractmethod
    async def get_workflow_run_bundle(self, run_id: str) -> WorkflowRunBundle:
        raise NotImplementedError

    @abstractmethod
    async def update_workflow_run_bundle(
        self,
        run_id: str,
        updater: Callable[[WorkflowRunBundle], WorkflowRunBundle | Awaitable[WorkflowRunBundle]],
    ) -> WorkflowRunBundle:
        raise NotImplementedError

    @abstractmethod
    async def get_node_run(self, run_id: str, node_key: str) -> WorkflowNodeRun:
        raise NotImplementedError
