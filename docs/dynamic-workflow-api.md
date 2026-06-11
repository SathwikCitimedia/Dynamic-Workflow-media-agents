# Dynamic Workflow API

This backend now supports dynamic human-in-the-loop workflow automation.

It keeps the legacy `/sessions` media workflow endpoints working, and adds a new dynamic platform built around:

- registered agents
- workflow definitions
- workflow runs
- node-level approve/reject/retry actions

`/sessions` is now a backward-compatibility wrapper over the seeded default workflow run.
New frontend integrations should use `/workflow-runs`.
Existing frontend integrations can continue using `/sessions`.
The legacy `/sessions` endpoints are hidden from Swagger/OpenAPI to avoid confusion for new frontend integrations.

## Recommended Frontend Integration Flow

Use only the dynamic APIs for all new frontend work.

Recommended API order:

1. `POST /agents`
2. `POST /workflows`
3. `POST /workflow-runs`
4. `GET /workflow-runs/{run_id}`
5. `WS /ws/workflow-runs/{run_id}`
6. `POST /workflow-runs/{run_id}/nodes/{node_key}/approve`
7. `POST /workflow-runs/{run_id}/nodes/{node_key}/reject`
8. `POST /workflow-runs/{run_id}/nodes/{node_key}/retry`
9. `POST /workflow-runs/{run_id}/cancel`

### Full Example: Create Agent

Request:

```http
POST /agents
Content-Type: application/json
```

```json
{
  "name": "Atlas Agent",
  "description": "Strategic brand intelligence agent",
  "endpoint_url": "https://aiagents.daisynova.com/api/agents/39/run",
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

Response:

```json
{
  "agent": {
    "id": "agent_abc123",
    "name": "Atlas Agent",
    "description": "Strategic brand intelligence agent",
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
    "updated_at": "2026-06-09T12:00:00Z"
  }
}
```

### Full Example: Create Workflow

Request:

```http
POST /workflows
Content-Type: application/json
```

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
    },
    {
      "node_key": "media_planner",
      "agent_id": "agent_media_planner",
      "display_name": "Media Planner",
      "approval_required": true,
      "input_template": {
        "task": "Create a media plan using this input: {{mapped_input}}"
      },
      "position": {"x": 400, "y": 200}
    }
  ],
  "edges": [
    {
      "source_node_key": "atlas",
      "target_node_key": "media_planner",
      "mapping": {
        "brand_intelligence": "$.approved_output"
      }
    },
    {
      "source_node_key": "audit",
      "target_node_key": "media_planner",
      "mapping": {
        "audit_findings": "$.approved_output"
      }
    }
  ]
}
```

Response:

```json
{
  "workflow": {
    "id": "workflow_xyz123",
    "name": "Media Campaign Workflow",
    "description": "Atlas + Audit, then Media Planner, then Geo + Meta",
    "version": 1,
    "enabled": true,
    "created_at": "2026-06-09T12:05:00Z",
    "updated_at": "2026-06-09T12:05:00Z"
  },
  "nodes": [
    {
      "id": "node_1",
      "workflow_id": "workflow_xyz123",
      "node_key": "atlas",
      "agent_id": "agent_atlas",
      "display_name": "Atlas Agent",
      "approval_required": true,
      "input_template_json": {
        "task": "Analyze this brand URL for strategic brand intelligence: {{initial_input.url}}"
      },
      "position_json": {"x": 100, "y": 100},
      "created_at": "2026-06-09T12:05:00Z",
      "updated_at": "2026-06-09T12:05:00Z"
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "workflow_id": "workflow_xyz123",
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
```

### Full Example: Start Workflow Run

Request:

```http
POST /workflow-runs
Content-Type: application/json
```

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

### Full Example: Get Workflow Run

Request:

```http
GET /workflow-runs/run_123
```

Response:

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
  "frontend_cards": [
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
  ],
  "workflow_graph": {
    "nodes": [
      {"id": "atlas", "label": "Atlas Agent", "status": "WAITING_FOR_APPROVAL"}
    ],
    "edges": [
      {"from": "atlas", "to": "media_planner"}
    ]
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
      "mapped_input_preview": null,
      "raw_output_json": {
        "content": {
          "summary": "Brand intelligence output"
        }
      },
      "approved_output_json": null,
      "user_feedback_history_json": [],
      "rejection_reason": null,
      "revision_count": 0,
      "error": null,
      "agent_session_id": null,
      "created_at": "2026-06-09T12:10:00Z",
      "updated_at": "2026-06-09T12:11:00Z"
    }
  }
}
```

### Full Example: Approve Node

Request:

```http
POST /workflow-runs/run_123/nodes/atlas/approve
Content-Type: application/json
```

```json
{}
```

### Full Example: Reject Node

Request:

```http
POST /workflow-runs/run_123/nodes/atlas/reject
Content-Type: application/json
```

```json
{
  "reason": "Please make this more detailed"
}
```

### Full Example: Retry Node

Request:

```http
POST /workflow-runs/run_123/nodes/atlas/retry
Content-Type: application/json
```

```json
{}
```

### Full Example: Cancel Workflow Run

Request:

```http
POST /workflow-runs/run_123/cancel
Content-Type: application/json
```

```json
{
  "reason": "User cancelled workflow"
}
```

## TypeScript Interfaces

```ts
export interface Agent {
  id: string;
  name: string;
  description: string | null;
  endpoint_url: string;
  method: string;
  headers_json: Record<string, unknown>;
  payload_template_json: Record<string, unknown>;
  response_mapping_json: Record<string, unknown>;
  auth_type: "none" | "bearer";
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  version: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface FrontendCard {
  node_key: string;
  title: string;
  status:
    | "PENDING"
    | "RUNNING"
    | "WAITING_FOR_APPROVAL"
    | "APPROVED"
    | "FAILED"
    | "CANCELLED"
    | "SKIPPED";
  summary: string;
  output: unknown;
  mapped_input_preview: unknown | null;
  available_actions: Array<"approve" | "reject" | "retry">;
}

export interface WorkflowGraphNode {
  id: string;
  label: string;
  status: string;
}

export interface WorkflowGraphEdge {
  from: string;
  to: string;
}

export interface WorkflowGraph {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
}

export interface NodeRun {
  id: string;
  workflow_run_id: string;
  node_key: string;
  agent_id: string;
  status: string;
  input_task: string | null;
  input_payload_json: Record<string, unknown> | null;
  mapped_input_preview: unknown | null;
  raw_output_json: unknown;
  approved_output_json: unknown;
  user_feedback_history_json: string[];
  rejection_reason: string | null;
  revision_count: number;
  error: string | null;
  agent_session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRunResponse {
  run: {
    id: string;
    workflow_id: string;
    status: "RUNNING" | "WAITING_FOR_APPROVAL" | "COMPLETED" | "FAILED" | "CANCELLED";
    initial_input_json: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };
  current_stage: string;
  progress: {
    total_nodes: number;
    completed_nodes: number;
    waiting_for_approval_nodes: string[];
    running_nodes: string[];
    failed_nodes: string[];
  };
  frontend_cards: FrontendCard[];
  workflow_graph: WorkflowGraph;
  available_actions: string[];
  node_runs: Record<string, NodeRun>;
}
```

## Fetch Examples

```ts
const API_BASE = "http://localhost:8000";

export async function createAgent(payload: {
  name: string;
  description?: string;
  endpoint_url: string;
  method?: string;
  auth_type?: "none" | "bearer";
  headers?: Record<string, unknown>;
  payload_template?: Record<string, unknown>;
  response_mapping?: Record<string, unknown>;
  enabled?: boolean;
}) {
  const response = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Failed to create agent");
  return response.json();
}

export async function createWorkflow(payload: {
  name: string;
  description?: string;
  version?: number;
  enabled?: boolean;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}) {
  const response = await fetch(`${API_BASE}/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Failed to create workflow");
  return response.json();
}

export async function startWorkflowRun(payload: {
  workflow_id: string;
  input: Record<string, unknown>;
}): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Failed to start workflow run");
  return response.json();
}

export async function getWorkflowRun(runId: string): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs/${runId}`);
  if (!response.ok) throw new Error("Failed to fetch workflow run");
  return response.json();
}

export async function approveNode(runId: string, nodeKey: string): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs/${runId}/nodes/${nodeKey}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) throw new Error("Failed to approve node");
  return response.json();
}

export async function rejectNode(
  runId: string,
  nodeKey: string,
  reason: string,
): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs/${runId}/nodes/${nodeKey}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) throw new Error("Failed to reject node");
  return response.json();
}

export async function retryNode(runId: string, nodeKey: string): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs/${runId}/nodes/${nodeKey}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) throw new Error("Failed to retry node");
  return response.json();
}

export async function cancelWorkflowRun(
  runId: string,
  reason: string,
): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/workflow-runs/${runId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) throw new Error("Failed to cancel workflow run");
  return response.json();
}

export function connectWorkflowSocket(
  runId: string,
  onEvent: (event: unknown) => void,
): WebSocket {
  const socket = new WebSocket(`ws://localhost:8000/ws/workflow-runs/${runId}`);
  socket.onmessage = (message) => {
    onEvent(JSON.parse(message.data));
  };
  return socket;
}
```

## Frontend Rendering Rules

- Render cards from `frontend_cards`
- Render graph from `workflow_graph`
- Show buttons only from each card's `available_actions`
- Approve sends `{}`
- Reject sends `{ "reason": "..." }`
- Retry sends `{}`
- Use `node_runs` for detailed state, debug, and raw/approved output inspection
- Use top-level `available_actions` for run-level actions like cancel
- Prefer WebSocket updates for live UX, and use `GET /workflow-runs/{run_id}` as polling fallback
- `/sessions` is legacy only and should not be used for new frontend code
- `/sessions` still exists for backward compatibility, but it is intentionally hidden from Swagger

## Core Concepts

### Agent

A reusable external API configuration.

### Workflow

A DAG of workflow nodes and workflow edges.

### Workflow Node

An agent placed inside a workflow definition.

### Workflow Edge

A dependency and output-mapping relationship between nodes.

### Workflow Run

One execution of a workflow.

### Node Run

One execution state for a workflow node inside a workflow run.

## Seeded Default Media Workflow

The app seeds these agents on first use:

- `agent_atlas`
- `agent_audit`
- `agent_media_planner`
- `agent_geo_fence`
- `agent_meta`

It also seeds the default workflow:

- `workflow_media_campaign`

Flow:

1. `atlas` and `audit` run in parallel
2. after both are approved, `media_planner` runs
3. after `media_planner` is approved, `geo_fence` and `meta` run in parallel

## Agent APIs

### `POST /agents`

Register a reusable agent.

Example:

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

### `GET /agents`

Returns all registered agents.

For seeded media agents, the response also includes compatibility fields such as:

- `step_id`
- `agent_id`
- `transport`
- `endpoint`

### `GET /agents/{agent_id}`

Fetch one registered agent.

### `PATCH /agents/{agent_id}`

Update an agent.

### `DELETE /agents/{agent_id}`

Delete an agent.

## Workflow Definition APIs

### `POST /workflows`

Create a workflow definition.

Example:

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
  "edges": []
}
```

### `GET /workflows`

List workflow definitions.

### `GET /workflows/{workflow_id}`

Get one workflow definition.

### `PATCH /workflows/{workflow_id}`

Update a workflow definition.

### `DELETE /workflows/{workflow_id}`

Delete a workflow definition.

## DAG Validation Rules

Workflow creation/update rejects:

- duplicate `node_key`
- edges pointing to missing nodes
- cycles
- workflows with no start node
- nodes referencing missing agents
- nodes referencing disabled agents

## Workflow Run APIs

### `POST /workflow-runs`

Start a workflow run.

Example:

```json
{
  "workflow_id": "workflow_media_campaign",
  "input": {
    "url": "https://citimedia.in/"
  }
}
```

### `GET /workflow-runs`

List workflow runs.

### `GET /workflow-runs/{run_id}`

Returns the full frontend-ready run state:

```json
{
  "run": {},
  "current_stage": "ATLAS",
  "progress": {
    "total_nodes": 5,
    "completed_nodes": 0,
    "waiting_for_approval_nodes": [],
    "running_nodes": ["atlas", "audit"],
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

## Node Approval APIs

### `POST /workflow-runs/{run_id}/nodes/{node_key}/approve`

Approve node output.

Request body:

```json
{}
```

Behavior:

- only allowed from `WAITING_FOR_APPROVAL`
- if `approved_output` is omitted, backend extracts it from the node's `raw_output_json`
- node becomes `APPROVED`
- downstream runnable nodes start automatically

Optional override:

```json
{
  "approved_output": {
    "summary": "Optional manual override"
  }
}
```

### `POST /workflow-runs/{run_id}/nodes/{node_key}/reject`

Reject means regenerate the same node.

Request:

```json
{
  "reason": "Please make this more detailed"
}
```

Behavior:

- only allowed from `WAITING_FOR_APPROVAL`
- saves feedback in `user_feedback_history_json`
- increments `revision_count`
- reruns the same node
- does not trigger downstream nodes

### `POST /workflow-runs/{run_id}/nodes/{node_key}/retry`

Retry a failed node.

Behavior:

- only allowed from `FAILED`
- reruns the same node with its original rendered task

### `POST /workflow-runs/{run_id}/cancel`

Cancel the workflow run.

Request:

```json
{
  "reason": "User cancelled workflow"
}
```

Behavior:

- marks workflow run `CANCELLED`
- pending nodes are marked cancelled
- no downstream nodes continue

## Execution Rules

1. Start nodes run in parallel.
2. A node becomes runnable only when all parents are `APPROVED`.
3. If a node requires approval, completion moves it to `WAITING_FOR_APPROVAL`.
4. If a node does not require approval, it auto-approves and downstream execution continues.

## Mapping and Templates

### Supported mapping expressions

- `$.approved_output`
- `$.approved_output.field`
- `$.raw_output.content`
- `$.initial_input.url`

### Supported template variables

- `{{initial_input.url}}`
- `{{mapped_input}}`
- `{{parent_outputs}}`
- `{{task}}`
- `{{agent_session_id}}`
- `{{env.DAISYNOVA_API_TOKEN}}`

## Frontend Rendering Contract

### `frontend_cards`

One card per workflow node:

```json
{
  "node_key": "atlas",
  "title": "Atlas Agent",
  "status": "WAITING_FOR_APPROVAL",
  "summary": "Short frontend summary",
  "output": {},
  "mapped_input_preview": null,
  "available_actions": ["approve", "reject"]
}
```

### `workflow_graph`

```json
{
  "nodes": [
    {"id": "atlas", "label": "Atlas Agent", "status": "WAITING_FOR_APPROVAL"}
  ],
  "edges": [
    {"from": "atlas", "to": "media_planner"}
  ]
}
```

### `available_actions`

Per node:

- `WAITING_FOR_APPROVAL` -> `["approve", "reject"]`
- `FAILED` -> `["retry"]`
- all other states -> `[]`

Top-level run actions:

- active run -> `["cancel"]`
- completed or cancelled run -> `[]`

## WebSocket

### `WS /ws/workflow-runs/{run_id}`

The server broadcasts dynamic workflow events such as:

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

## Legacy Compatibility

The legacy media workflow endpoints still exist:

- `POST /sessions`
- `GET /sessions/{session_id}`
- approve/reject/retry/cancel session step endpoints

These remain available so the existing frontend can continue to work while new clients move to the dynamic workflow APIs.
They are hidden from Swagger/OpenAPI so new integrations are guided toward `/workflow-runs`.
