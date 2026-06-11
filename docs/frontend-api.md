# Frontend API Documentation

This document is the frontend handoff for the current FastAPI workflow backend.

Use the dynamic workflow APIs for all new frontend work:

- `/health`
- `/agents`
- `/workflows`
- `/workflow-runs`
- `WS /ws/workflow-runs/{run_id}`

Legacy `/sessions` endpoints still exist for backward compatibility, but they are hidden from Swagger and should not be used for new UI work.

## Base URL

Local development:

```text
http://127.0.0.1:8000
```

Swagger/OpenAPI:

```text
GET /docs
GET /openapi.json
```

## Recommended Frontend Flow

Recommended order:

1. Register agents with `POST /agents`
2. Create a workflow DAG with `POST /workflows`
3. Start execution with `POST /workflow-runs`
4. Poll with `GET /workflow-runs/{run_id}`
5. Subscribe to `WS /ws/workflow-runs/{run_id}` for live updates
6. Use approve/reject/retry/cancel actions based on `available_actions`

If your frontend only needs the seeded media flow, you can skip agent and workflow creation and directly start:

```json
{
  "workflow_id": "workflow_media_campaign",
  "input": {
    "url": "https://example.com"
  }
}
```

## Authentication

The frontend does not send DaisyNova credentials directly.

The backend uses environment-based credentials such as:

```text
DAISYNOVA_API_TOKEN
```

If agent execution fails and `ALLOW_AGENT_MOCK_FALLBACK=true`, the backend may return fallback output marked with:

```json
{
  "is_mock": true
}
```

Frontend should clearly surface that as development/fallback data.

## Core Concepts

### Agent

A reusable external API definition.

### Workflow

A DAG of nodes and edges.

### Workflow Run

One execution of a workflow definition.

### Node Run

The runtime state for one node inside a workflow run.

### `run_id`

The main ID the frontend should store and use for:

- `GET /workflow-runs/{run_id}`
- node approve/reject/retry
- workflow cancel
- WebSocket subscription

### `node_key`

The node identifier inside a workflow, such as:

- `atlas`
- `audit`
- `media_planner`
- `geo_fence`
- `meta`

### Node Statuses

- `PENDING`
- `RUNNING`
- `WAITING_FOR_APPROVAL`
- `APPROVED`
- `FAILED`
- `CANCELLED`
- `SKIPPED`

### Workflow Statuses

- `RUNNING`
- `WAITING_FOR_APPROVAL`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

## Main Endpoints

### `GET /health`

Response:

```json
{
  "status": "ok"
}
```

### `GET /agents`

Returns registered agents.

Example:

```json
{
  "agents": [
    {
      "id": "agent_atlas",
      "name": "Atlas Agent",
      "description": "Strategic brand intelligence analysis",
      "endpoint_url": "https://aiagents.daisynova.com/api/agents/39/run",
      "method": "POST",
      "headers_json": {
        "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
        "Content-Type": "application/json"
      },
      "payload_template_json": {
        "task": "{{task}}",
        "session_id": "{{agent_session_id}}",
        "wait": true
      },
      "response_mapping_json": {
        "content": "$.content"
      },
      "auth_type": "bearer",
      "enabled": true,
      "created_at": "2026-06-09T12:00:00Z",
      "updated_at": "2026-06-09T12:00:00Z",
      "step_id": "atlas",
      "agent_id": 39,
      "transport": "run",
      "endpoint": "https://aiagents.daisynova.com/api/agents/39/run"
    }
  ]
}
```

Notes:

- seeded media agents include compatibility fields like `step_id`, `agent_id`, `transport`, and `endpoint`
- frontend can ignore those if it only cares about the generic dynamic model

### `POST /agents`

Registers a reusable external API config.

Request:

```json
{
  "name": "Meta Ads Agent",
  "description": "Creates Meta campaign plan",
  "endpoint_url": "https://aiagents.daisynova.com/api/agents/70/run",
  "method": "POST",
  "auth_type": "bearer",
  "headers": {
    "Authorization": "Bearer {{env.DAISYNOVA_API_TOKEN}}",
    "Content-Type": "application/json"
  },
  "payload_template": {
    "task": "{{task}}",
    "session_id": "{{agent_session_id}}",
    "wait": true
  },
  "response_mapping": {
    "content": "$.content"
  },
  "enabled": true
}
```

### `GET /workflows`

Returns workflow definitions.

Example:

```json
{
  "workflows": [
    {
      "workflow": {
        "id": "workflow_media_campaign",
        "name": "Media Campaign Workflow",
        "description": "Atlas + Audit, then Media Planner, then Geo + Meta",
        "version": 1,
        "enabled": true,
        "created_at": "2026-06-09T12:05:00Z",
        "updated_at": "2026-06-09T12:05:00Z"
      },
      "nodes": [
        {
          "id": "node_atlas",
          "workflow_id": "workflow_media_campaign",
          "node_key": "atlas",
          "agent_id": "agent_atlas",
          "display_name": "Atlas Agent",
          "approval_required": true,
          "input_template_json": {
            "task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"
          },
          "position_json": {
            "x": 100,
            "y": 100
          },
          "created_at": "2026-06-09T12:05:00Z",
          "updated_at": "2026-06-09T12:05:00Z"
        }
      ],
      "edges": [
        {
          "id": "edge_atlas_media",
          "workflow_id": "workflow_media_campaign",
          "source_node_key": "atlas",
          "target_node_key": "media_planner",
          "mapping_json": {
            "brand_intelligence": "$.approved_output"
          },
          "created_at": "2026-06-09T12:05:00Z",
          "updated_at": "2026-06-09T12:05:00Z"
        }
      ]
    }
  ]
}
```

### `POST /workflows`

Creates a DAG workflow definition.

Request:

```json
{
  "name": "Media Campaign Workflow",
  "description": "Atlas + Audit, then Media Planner, then Geo + Meta",
  "nodes": [
    {
      "node_key": "atlas",
      "agent_id": "agent_atlas",
      "display_name": "Atlas Agent",
      "approval_required": true,
      "input_template": {
        "task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"
      },
      "position": {"x": 100, "y": 100}
    },
    {
      "node_key": "audit",
      "agent_id": "agent_audit",
      "display_name": "Audit Agent",
      "approval_required": true,
      "input_template": {
        "task": "Perform a detailed brand audit for this URL: {{initial_input.url}}"
      },
      "position": {"x": 100, "y": 300}
    }
  ],
  "edges": [
    {
      "source_node_key": "atlas",
      "target_node_key": "media_planner",
      "mapping": {
        "brand_intelligence": "$.approved_output"
      }
    }
  ]
}
```

Validation notes:

- duplicate `node_key` values are rejected
- cycles are rejected
- edges pointing to missing nodes are rejected
- disabled or missing agents are rejected

### `POST /workflow-runs`

Starts a workflow run.

Request:

```json
{
  "workflow_id": "workflow_media_campaign",
  "input": {
    "url": "https://citimedia.in/"
  }
}
```

Response:

```json
{
  "run": {
    "id": "run_123",
    "workflow_id": "workflow_media_campaign",
    "status": "RUNNING",
    "initial_input_json": {
      "url": "https://citimedia.in/"
    },
    "created_at": "2026-06-09T12:10:00Z",
    "updated_at": "2026-06-09T12:10:00Z"
  },
  "current_stage": "ATLAS",
  "progress": {
    "total_nodes": 5,
    "completed_nodes": 0,
    "waiting_for_approval_nodes": [],
    "running_nodes": ["atlas", "audit"],
    "failed_nodes": []
  },
  "frontend_cards": [
    {
      "node_key": "atlas",
      "title": "Atlas Agent",
      "status": "RUNNING",
      "summary": "",
      "output": {},
      "mapped_input_preview": null,
      "available_actions": []
    }
  ],
  "workflow_graph": {
    "nodes": [
      {"id": "atlas", "label": "Atlas Agent", "status": "RUNNING"},
      {"id": "audit", "label": "Audit Agent", "status": "RUNNING"}
    ],
    "edges": [
      {"from": "atlas", "to": "media_planner"},
      {"from": "audit", "to": "media_planner"}
    ]
  },
  "available_actions": ["cancel"],
  "node_runs": {
    "atlas": {
      "id": "node_run_1",
      "workflow_run_id": "run_123",
      "node_key": "atlas",
      "agent_id": "agent_atlas",
      "status": "RUNNING",
      "input_task": "Analyze this brand URL for strategic brand intelligence: https://citimedia.in/",
      "input_payload_json": {
        "task": "Analyze this brand URL for strategic brand intelligence: https://citimedia.in/"
      },
      "mapped_input_preview": null,
      "raw_output_json": null,
      "approved_output_json": null,
      "user_feedback_history_json": [],
      "rejection_reason": null,
      "revision_count": 0,
      "error": null,
      "agent_session_id": null,
      "created_at": "2026-06-09T12:10:00Z",
      "updated_at": "2026-06-09T12:10:00Z"
    }
  }
}
```

### `GET /workflow-runs/{run_id}`

This is the main polling endpoint for the frontend.

It returns:

- top-level run metadata
- current stage
- progress summary
- `frontend_cards` for easy UI rendering
- `workflow_graph` for DAG rendering
- `available_actions` for run-level UI
- `node_runs` for detailed state/debug information

## WorkflowRunResponse Contract

```json
{
  "run": {
    "id": "run_123",
    "workflow_id": "workflow_media_campaign",
    "status": "WAITING_FOR_APPROVAL",
    "initial_input_json": {
      "url": "https://citimedia.in/"
    },
    "created_at": "2026-06-09T12:10:00Z",
    "updated_at": "2026-06-09T12:11:00Z"
  },
  "current_stage": "INITIAL_ANALYSIS",
  "progress": {
    "total_nodes": 5,
    "completed_nodes": 0,
    "waiting_for_approval_nodes": ["atlas", "audit"],
    "running_nodes": [],
    "failed_nodes": []
  },
  "frontend_cards": [],
  "workflow_graph": {
    "nodes": [],
    "edges": []
  },
  "available_actions": ["cancel"],
  "node_runs": {}
}
```

## Node Actions

### `POST /workflow-runs/{run_id}/nodes/{node_key}/approve`

Request:

```json
{}
```

Optional override:

```json
{
  "approved_output": {
    "summary": "Optional manual override"
  }
}
```

Behavior:

- only allowed when node status is `WAITING_FOR_APPROVAL`
- if omitted, `approved_output_json` is automatically extracted from `raw_output_json`
- approving a node may automatically unlock downstream nodes

### `POST /workflow-runs/{run_id}/nodes/{node_key}/reject`

Request:

```json
{
  "reason": "Please make this more detailed"
}
```

Behavior:

- only allowed when node status is `WAITING_FOR_APPROVAL`
- rejects the current output and regenerates the same node
- does not advance downstream
- appends to `user_feedback_history_json`
- increments `revision_count`

### `POST /workflow-runs/{run_id}/nodes/{node_key}/retry`

Request:

```json
{}
```

Behavior:

- only allowed when node status is `FAILED`
- retries the same node with its original task

### `POST /workflow-runs/{run_id}/cancel`

Request:

```json
{
  "reason": "User cancelled workflow"
}
```

Behavior:

- marks the workflow run as `CANCELLED`
- prevents further downstream execution

## Frontend Rendering Rules

### Render cards from `frontend_cards`

Each item is already a UI-focused projection:

```json
{
  "node_key": "atlas",
  "title": "Atlas Agent",
  "status": "WAITING_FOR_APPROVAL",
  "summary": "Brand intelligence output",
  "output": {
    "content": {
      "summary": "Brand intelligence output"
    }
  },
  "mapped_input_preview": null,
  "available_actions": ["approve", "reject"]
}
```

Recommended UI behavior:

1. show `title`
2. show `status`
3. show `summary`
4. show `mapped_input_preview` for downstream/running nodes when useful
5. show full `output` in expand/debug views

### Render graph from `workflow_graph`

```json
{
  "nodes": [
    {"id": "atlas", "label": "Atlas Agent", "status": "APPROVED"},
    {"id": "audit", "label": "Audit Agent", "status": "APPROVED"},
    {"id": "media_planner", "label": "Media Planner", "status": "WAITING_FOR_APPROVAL"}
  ],
  "edges": [
    {"from": "atlas", "to": "media_planner"},
    {"from": "audit", "to": "media_planner"}
  ]
}
```

Use this directly for:

- DAG graph views
- pipeline progress UIs
- dependency lines

### Show buttons only from `available_actions`

Per card:

- `["approve", "reject"]` means show Approve and Reject buttons
- `["retry"]` means show Retry
- `[]` means show no node action buttons

Top-level `available_actions` is for workflow-run-level actions like cancel.

### Action payload rules

- approve sends `{}` by default
- reject sends `{ "reason": "..." }`
- retry sends `{}`
- cancel sends `{ "reason": "..." }`

Do not reconstruct approval logic in the frontend.
Use `available_actions` as the source of truth.

## Progress Object

```json
{
  "total_nodes": 5,
  "completed_nodes": 2,
  "waiting_for_approval_nodes": ["media_planner"],
  "running_nodes": [],
  "failed_nodes": []
}
```

Use this for:

- progress bars
- counters
- stage badges
- review queues

## Node Run Details

`node_runs` is the detailed runtime map keyed by `node_key`.

Useful fields:

- `status`
- `input_task`
- `input_payload_json`
- `mapped_input_preview`
- `raw_output_json`
- `approved_output_json`
- `user_feedback_history_json`
- `revision_count`
- `error`
- `agent_session_id`

### `agent_session_id`

This is the upstream external-agent thread/session ID when available.

Frontend usually does not need to send it back manually.
It is exposed mainly for transparency and debugging.

## WebSocket

Endpoint:

```text
WS /ws/workflow-runs/{run_id}
```

The backend broadcasts dynamic workflow events such as:

- `NODE_STARTED`
- `NODE_COMPLETED`
- `NODE_WAITING_APPROVAL`
- `NODE_APPROVED`
- `NODE_REJECTED_REGENERATING`
- `NODE_FAILED`
- `WORKFLOW_COMPLETED`
- `WORKFLOW_CANCELLED`
- `WORKFLOW_FAILED`

Event shape:

```json
{
  "type": "NODE_WAITING_APPROVAL",
  "run_id": "run_123",
  "node_key": "atlas",
  "status": "WAITING_FOR_APPROVAL",
  "workflow_status": "WAITING_FOR_APPROVAL",
  "payload": {}
}
```

Recommendation:

- use WebSocket for instant updates
- keep `GET /workflow-runs/{run_id}` as polling fallback

## Current Stage Behavior

`current_stage` is a frontend-friendly stage marker.

For dynamic workflows it is currently derived from runtime state.
Examples:

- `ATLAS`
- `AUDIT`
- `INITIAL_ANALYSIS`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

Frontend should treat it as display metadata, not as a strict dependency engine.

## Seeded Default Media Workflow

Seeded agents:

- `agent_atlas`
- `agent_audit`
- `agent_media_planner`
- `agent_geo_fence`
- `agent_meta`

Seeded workflow:

- `workflow_media_campaign`

Execution order:

1. `atlas` and `audit` run in parallel
2. after both are approved, `media_planner` runs
3. after `media_planner` is approved, `geo_fence` and `meta` run in parallel

## Mock Fallback Behavior

When `ALLOW_AGENT_MOCK_FALLBACK=true`, a failed agent may return fallback output like:

```json
{
  "content": "Mock fallback output for atlas. Real agent call failed: ...",
  "is_mock": true,
  "original_error": "..."
}
```

Frontend should visibly label this as fallback/mock output.

## Error Cases

### `409 Conflict`

Common cases:

- approving a node that is not `WAITING_FOR_APPROVAL`
- rejecting a node that is not `WAITING_FOR_APPROVAL`
- retrying a node that is not `FAILED`
- changing a cancelled workflow run

Typical response:

```json
{
  "detail": "Node is not waiting for approval."
}
```

### Validation errors

Examples:

- invalid URL in run input or session input
- empty reject reason
- empty cancel reason
- malformed workflow definition

These return standard FastAPI validation responses.

## Frontend Implementation Recommendations

### For polling

Recommended flow:

1. call `POST /workflow-runs`
2. store `run_id`
3. poll `GET /workflow-runs/{run_id}`
4. slow or stop polling when:
   - `run.status = COMPLETED`
   - `run.status = FAILED`
   - `run.status = CANCELLED`

### For rendering actions

Use `available_actions` directly instead of re-implementing rules.

### For debug views

Useful fields:

- `node_runs[node_key].input_task`
- `node_runs[node_key].input_payload_json`
- `node_runs[node_key].mapped_input_preview`
- `node_runs[node_key].agent_session_id`
- `node_runs[node_key].raw_output_json`

### For workflow dashboards

Useful endpoints:

- `GET /workflows`
- `GET /workflow-runs`
- `GET /workflow-runs/{run_id}`

## Legacy Compatibility

Legacy endpoints still exist:

- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/recent`
- legacy approve/reject/retry/cancel session routes

Important:

- they are wrappers over the seeded dynamic workflow engine
- they are hidden from Swagger/OpenAPI
- they are for backward compatibility only
- new frontend integrations should use `/workflow-runs`
