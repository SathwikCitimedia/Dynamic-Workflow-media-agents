import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.seed.media_workflow import DEFAULT_MEDIA_WORKFLOW_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DynamicSuccessAgentClient:
    def __init__(self):
        self.calls: list[dict] = []

    async def run_agent(self, agent, task, user_id, agent_session_id=None):
        await asyncio.sleep(0.01)
        return {"content": {"agent": agent.step_id, "task": task, "user_id": user_id}, "raw": {"ok": True}}

    async def run_registered_agent(self, agent, *, context, timeout_seconds=180.0, max_retries=3, backoff_base_seconds=0.5):
        self.calls.append({"agent_id": agent.id, "task": context["task"], "started_at": time.perf_counter()})
        await asyncio.sleep(0.02)
        return {
            "content": {
                "agent_id": agent.id,
                "task": context["task"],
                "mapped_input": context.get("mapped_input"),
            },
            "raw": {"ok": True},
        }


async def wait_for_node_status(client: AsyncClient, run_id: str, node_key: str, expected_status: str):
    for _ in range(40):
        response = await client.get(f"/workflow-runs/{run_id}")
        payload = response.json()
        if payload["node_runs"][node_key]["status"] == expected_status:
            return payload
        await asyncio.sleep(0.02)
    raise AssertionError(f"Node {node_key} did not reach {expected_status}")


@pytest.mark.anyio
async def test_create_agent():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/agents",
            json={
                "name": "Test Agent",
                "description": "Dynamic test agent",
                "endpoint_url": "https://example.com/run",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload_template": {"task": "{{task}}"},
                "response_mapping": {"content": "$.content"},
                "auth_type": "none",
                "enabled": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["agent"]["name"] == "Test Agent"


@pytest.mark.anyio
async def test_create_workflow():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        agent = (
            await client.post(
                "/agents",
                json={
                    "name": "Test Agent",
                    "endpoint_url": "https://example.com/run",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "payload_template": {"task": "{{task}}"},
                    "response_mapping": {"content": "$.content"},
                    "auth_type": "none",
                    "enabled": True,
                },
            )
        ).json()["agent"]
        response = await client.post(
            "/workflows",
            json={
                "name": "One Node Workflow",
                "description": "Simple workflow",
                "nodes": [
                    {
                        "node_key": "start",
                        "agent_id": agent["id"],
                        "display_name": "Start Node",
                        "approval_required": True,
                        "input_template": {"task": "Run this for {{initial_input.url}}"},
                        "position": {"x": 0, "y": 0},
                    }
                ],
                "edges": [],
            },
        )

    assert response.status_code == 200
    assert response.json()["workflow"]["name"] == "One Node Workflow"


@pytest.mark.anyio
async def test_reject_cyclic_workflow():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        agent = (
            await client.post(
                "/agents",
                json={
                    "name": "Cycle Agent",
                    "endpoint_url": "https://example.com/run",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "payload_template": {"task": "{{task}}"},
                    "response_mapping": {"content": "$.content"},
                    "auth_type": "none",
                    "enabled": True,
                },
            )
        ).json()["agent"]
        response = await client.post(
            "/workflows",
            json={
                "name": "Cyclic Workflow",
                "nodes": [
                    {"node_key": "a", "agent_id": agent["id"], "display_name": "A", "input_template": {"task": "A"}},
                    {"node_key": "b", "agent_id": agent["id"], "display_name": "B", "input_template": {"task": "B"}},
                ],
                "edges": [
                    {"source_node_key": "a", "target_node_key": "b", "mapping": {}},
                    {"source_node_key": "b", "target_node_key": "a", "mapping": {}},
                ],
            },
        )

    assert response.status_code == 400
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_execute_start_nodes_in_parallel():
    agent_client = DynamicSuccessAgentClient()
    app = create_app(agent_client=agent_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/workflow-runs",
            json={"workflow_id": DEFAULT_MEDIA_WORKFLOW_ID, "input": {"url": "https://example.com"}},
        )
        run_id = response.json()["run"]["id"]
        await wait_for_node_status(client, run_id, "atlas", "WAITING_FOR_APPROVAL")
        await wait_for_node_status(client, run_id, "audit", "WAITING_FOR_APPROVAL")

    atlas_call = next(call for call in agent_client.calls if call["agent_id"] == "agent_atlas")
    audit_call = next(call for call in agent_client.calls if call["agent_id"] == "agent_audit")
    assert abs(atlas_call["started_at"] - audit_call["started_at"]) < 0.03


@pytest.mark.anyio
async def test_downstream_node_waits_for_all_parents_approved():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/workflow-runs",
            json={"workflow_id": DEFAULT_MEDIA_WORKFLOW_ID, "input": {"url": "https://example.com"}},
        )
        run_id = response.json()["run"]["id"]
        await wait_for_node_status(client, run_id, "atlas", "WAITING_FOR_APPROVAL")
        await wait_for_node_status(client, run_id, "audit", "WAITING_FOR_APPROVAL")

        await client.post(f"/workflow-runs/{run_id}/nodes/atlas/approve", json={})
        mid = (await client.get(f"/workflow-runs/{run_id}")).json()
        assert mid["node_runs"]["media_planner"]["status"] == "PENDING"

        await client.post(f"/workflow-runs/{run_id}/nodes/audit/approve", json={})
        final = await wait_for_node_status(client, run_id, "media_planner", "WAITING_FOR_APPROVAL")

    assert final["node_runs"]["media_planner"]["status"] == "WAITING_FOR_APPROVAL"


@pytest.mark.anyio
async def test_reject_regenerates_same_node():
    agent_client = DynamicSuccessAgentClient()
    app = create_app(agent_client=agent_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/workflow-runs",
            json={"workflow_id": DEFAULT_MEDIA_WORKFLOW_ID, "input": {"url": "https://example.com"}},
        )
        run_id = response.json()["run"]["id"]
        await wait_for_node_status(client, run_id, "atlas", "WAITING_FOR_APPROVAL")
        reject = await client.post(
            f"/workflow-runs/{run_id}/nodes/atlas/reject",
            json={"reason": "Please regenerate"},
        )
        assert reject.status_code == 200
        payload = await wait_for_node_status(client, run_id, "atlas", "WAITING_FOR_APPROVAL")

    assert payload["node_runs"]["atlas"]["revision_count"] == 1
    assert len([call for call in agent_client.calls if call["agent_id"] == "agent_atlas"]) == 2


@pytest.mark.anyio
async def test_approved_node_cannot_be_changed():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/workflow-runs",
            json={"workflow_id": DEFAULT_MEDIA_WORKFLOW_ID, "input": {"url": "https://example.com"}},
        )
        run_id = response.json()["run"]["id"]
        await wait_for_node_status(client, run_id, "atlas", "WAITING_FOR_APPROVAL")
        await client.post(f"/workflow-runs/{run_id}/nodes/atlas/approve", json={})
        reject = await client.post(
            f"/workflow-runs/{run_id}/nodes/atlas/reject",
            json={"reason": "Try again"},
        )

    assert reject.status_code == 409


@pytest.mark.anyio
async def test_dynamic_frontend_cards():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/workflow-runs",
            json={"workflow_id": DEFAULT_MEDIA_WORKFLOW_ID, "input": {"url": "https://example.com"}},
        )
        run_id = response.json()["run"]["id"]
        payload = (await client.get(f"/workflow-runs/{run_id}")).json()

    assert response.status_code == 201
    assert len(payload["frontend_cards"]) == 5
    card = next(card for card in payload["frontend_cards"] if card["node_key"] == "atlas")
    assert card["title"] == "Atlas Agent"
    assert "available_actions" in card
    assert len(payload["workflow_graph"]["nodes"]) == 5


@pytest.mark.anyio
async def test_default_media_workflow_seed_works():
    app = create_app(agent_client=DynamicSuccessAgentClient())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(f"/workflows/{DEFAULT_MEDIA_WORKFLOW_ID}")

    assert response.status_code == 200
    assert response.json()["workflow"]["id"] == DEFAULT_MEDIA_WORKFLOW_ID
