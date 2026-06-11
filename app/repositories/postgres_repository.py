from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.repositories.base import BaseDynamicRepository


class Base(DeclarativeBase):
    pass


class AgentORM(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    headers_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    payload_template_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    response_mapping_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowORM(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowNodeORM(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    input_template_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    position_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowEdgeORM(Base):
    __tablename__ = "workflow_edges"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    target_node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    mapping_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowRunORM(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    initial_input_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowNodeRunORM(Base):
    __tablename__ = "workflow_node_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    raw_output_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    approved_output_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    user_feedback_history_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgresDynamicRepository(BaseDynamicRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def create_agent(self, agent):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def list_agents(self):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def get_agent(self, agent_id: str):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def update_agent(self, agent_id: str, updater):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def delete_agent(self, agent_id: str) -> None:
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def save_workflow_bundle(self, bundle):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def list_workflow_bundles(self):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def get_workflow_bundle(self, workflow_id: str):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def delete_workflow_bundle(self, workflow_id: str) -> None:
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def create_workflow_run_bundle(self, bundle):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def list_workflow_run_bundles(self):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def get_workflow_run_bundle(self, run_id: str):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def update_workflow_run_bundle(self, run_id: str, updater):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")

    async def get_node_run(self, run_id: str, node_key: str):
        raise NotImplementedError("Postgres dynamic repository is not implemented yet.")
