from __future__ import annotations

from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.models import AgentDefinition, WorkflowBundle


class DagService:
    def validate(self, bundle: WorkflowBundle, agents: dict[str, AgentDefinition]) -> None:
        node_keys = [node.node_key for node in bundle.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow contains duplicate node_key values.",
            )

        node_map = {node.node_key: node for node in bundle.nodes}
        if not node_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow must contain at least one node.",
            )

        incoming_counts = {node_key: 0 for node_key in node_map}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in bundle.edges:
            if edge.source_node_key not in node_map or edge.target_node_key not in node_map:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workflow edge points to a missing node.",
                )
            adjacency[edge.source_node_key].append(edge.target_node_key)
            incoming_counts[edge.target_node_key] += 1

        for node in bundle.nodes:
            agent = agents.get(node.agent_id)
            if agent is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Workflow node '{node.node_key}' references a missing agent.",
                )
            if not agent.enabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Workflow node '{node.node_key}' references a disabled agent.",
                )

        queue = deque([node_key for node_key, count in incoming_counts.items() if count == 0])
        visited = 0
        counts = dict(incoming_counts)
        while queue:
            node_key = queue.popleft()
            visited += 1
            for target in adjacency.get(node_key, []):
                counts[target] -= 1
                if counts[target] == 0:
                    queue.append(target)

        if visited != len(node_map):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow contains a cycle.",
            )

        if not any(count == 0 for count in incoming_counts.values()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow must contain at least one start node.",
            )

    def start_node_keys(self, bundle: WorkflowBundle) -> list[str]:
        targets = {edge.target_node_key for edge in bundle.edges}
        return [node.node_key for node in bundle.nodes if node.node_key not in targets]

    def parent_edges(self, bundle: WorkflowBundle, node_key: str) -> list:
        return [edge for edge in bundle.edges if edge.target_node_key == node_key]

    def child_edges(self, bundle: WorkflowBundle, node_key: str) -> list:
        return [edge for edge in bundle.edges if edge.source_node_key == node_key]
