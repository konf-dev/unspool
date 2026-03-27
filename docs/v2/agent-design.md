# Agent Design

## Hot Path — Conversational Agent

**File:** `src/agents/hot_path/graph.py`
**Framework:** LangGraph StateGraph
**Model:** Gemini 2.5 Flash (configurable via `CHAT_MODEL` env var)
**Provider:** Configurable via `CHAT_PROVIDER` env var
**Temperature:** 0.4
**Thinking Budget:** 4096 tokens
**Max Iterations:** 5

### State

```python
class HotPathState(TypedDict):
    user_id: str
    session_id: str
    messages: Annotated[list[AnyMessage], operator.add]
    iteration: int
    current_time_iso: str
    timezone: str
    context_string: str       # <context> XML block from graph
    trace_id: str
    profile: dict[str, Any]   # User preferences
```

### Graph Flow

```
START → agent → conditional → (tools → agent loop) → END
```

- `agent` node: Builds system prompt, invokes LLM with tool bindings
- `tools` node: Executes tool calls with user_id injection
- Conditional: If tool_calls present → tools; else or iteration > 5 → END

### Tools

#### `query_graph(semantic_query?, edge_type_filter?, node_type?, date_from?, date_to?)`

Searches the user's knowledge graph. Returns nodes with their edges.

- At least one of `semantic_query`, `edge_type_filter`, or `node_type` must be provided
- Semantic path: generates embedding via `gemini-embedding-001` (768d, L2-normalized, task_type=RETRIEVAL_QUERY), pgvector cosine distance search, limit 8
- Structural path (no `semantic_query`): SQL-only query by edge type / node type — no embedding API call
- Optional `edge_type_filter`: post-filters semantic results to nodes with matching outgoing edges
- Optional `node_type` filter: `memory`, `action`, `concept`, `person`, etc.
- Optional `date_from` / `date_to` (ISO8601): temporal filtering on edge metadata dates (deadline, logged_at)
- Returns up to 5 immediate edges per node for context (fetches 20 internally for post-filtering)
- On error: returns `"Error: ..."` string (consistent with mutate_graph)

**Response shape:**
```json
[
  {
    "id": "uuid",
    "item": "Buy groceries",
    "kind": "memory",
    "details": "status: open, due: 2026-03-25T17:00:00Z"
  }
]
```

#### `schedule_reminder(reminder_text, remind_at)`

Schedules a reminder for the user at a specific time.

- `reminder_text`: What to remind about
- `remind_at`: ISO8601 timestamp (LLM resolves natural language times using Current time + timezone from system prompt)
- Uses existing `ScheduledAction` + QStash `dispatch_at()` infrastructure
- Returns confirmation string with formatted time

#### `mutate_graph(action, node_id, value?, target_node_id?, edge_type?)`

Modifies the graph. 5 actions:

| Action | Required Params | What it Does |
|--------|----------------|--------------|
| `SET_STATUS` | node_id, value (`OPEN`/`DONE`) | Removes existing IS_STATUS edges, creates edge to status node |
| `ADD_EDGE` | node_id, target_node_id, edge_type | Upserts an edge between two nodes |
| `REMOVE_EDGE` | node_id, target_node_id, edge_type | Removes a specific edge |
| `UPDATE_CONTENT` | node_id, value (new text) | Changes a node's content text |
| `ARCHIVE` | node_id | Changes node_type to `archived_*` |

All mutations are event-first: append event to `event_stream`, then apply projection to graph tables, in the same transaction.

### user_id Injection

**Critical design decision:** `user_id` is NOT a tool parameter. The LLM never sees it. When the LLM calls `query_graph(semantic_query="thesis")`, the `call_tools()` function intercepts the call and injects `user_id` from LangGraph state before executing the real implementation (`_exec_query_graph`).

This eliminates:
- LLM hallucinating wrong user_ids
- LLM forgetting to pass user_id
- Security issues with user_id manipulation

### Tool Validation

`call_tools()` validates required arguments **before** dispatching to `_exec` functions:

- `query_graph`: `semantic_query` must be non-empty. Returns explicit error otherwise.
- `mutate_graph`: `action` and `node_id` must be non-empty. Returns explicit error listing missing params.

All tool errors are returned as `"Error: ..."` strings via `_sanitize_error()`, which translates Python exceptions (UUID parse errors, DB errors, connection timeouts) into LLM-readable messages. The LLM can distinguish errors from empty results and fall back to conversation context.

### Conversation Context Fallback

The system prompt instructs the LLM to use **both** graph memory and conversation history:
- If `query_graph` returns empty, respond from conversation context (the user may have just mentioned the info)
- If a tool returns an error, respond from conversation context
- If graph memory contradicts the conversation, clarify with the user before updating

### Context Assembly

**File:** `src/agents/hot_path/context.py`

`assemble_context()` runs 3 loaders in parallel via `asyncio.gather()` — **0 API calls, ~100ms total**:

1. **Profile** — User preferences from `user_profiles` table
2. **Recent Messages** — Last 20 messages from `vw_messages` view (reversed to chronological)
3. **Structured Items** — 5 concurrent SQL queries against graph views:
   - Overdue items (`get_slipped_items` — past soft/routine deadlines)
   - Plate items (`get_plate_items` — urgency-ordered, top 7)
   - Deadline calendar (`get_deadline_calendar` — today/tomorrow/this_week)
   - Metric summary (`get_metric_summary` — latest values per metric)
   - Recently done count (last 48h)

Each query catches its own exceptions — a failure in one doesn't block the others.

**Removed from init:** Semantic graph search (embedding API call + pgvector). Moved to `query_graph` tool only — the LLM calls it explicitly when needed.

Output: `<context>` XML block injected into system prompt.

### System Prompt

**File:** `src/agents/hot_path/system_prompt.py`
**Template:** `prompts/agent_system.md`
**Renderer:** Jinja2 SandboxedEnvironment with user input escaping

Variables injected:
- `{{ current_time }}` — User's local time from profile timezone
- `{{ profile }}` — Preferences dict (tone, length, pushiness, emoji, language)
- `{{ context }}` — `<context>` block from context assembly

## Cold Path — Background Archiver

**File:** `src/agents/cold_path/extractor.py`
**Model:** Gemini 2.5 Flash (configurable via `EXTRACTION_MODEL`)
**Provider:** Configurable via `EXTRACTION_PROVIDER`
**Temperature:** 0
**Thinking Budget:** 8192 tokens (high — graph quality is the foundation)
**Dispatch:** QStash (not asyncio.create_task)

### Extraction Pipeline

1. **Idempotency check** — SHA256 hash of `user_id:message` looked up in `event_stream` for `ColdPathProcessed` events
2. **LLM extraction** — Gemini with structured outputs (`response_json_schema` from Pydantic's `ExtractionResult.model_json_schema()`). Uses `system_instruction` to separate instructions from user content.
3. **Semantic dedup** — For each extracted node, search for existing nodes with same type using `SEMANTIC_SIMILARITY` task_type. If top-1 match has cosine distance < 0.1 (similarity > 0.9), reuse it.
4. **Batch node embedding** — All new nodes embedded in a single `embed_content()` call with `RETRIEVAL_DOCUMENT` task_type, then created via `get_or_create_node()`
5. **Edge creation** — `upsert_edge()` for all extracted relationships
6. **Mark processed** — Append `ColdPathProcessed` event with idempotency key

### Extraction Schema

```python
class NodeMetadata:
    entities: list[dict]   # [{"text": "Mom", "likely": "person"}]
    temporal: dict         # {"tense": "past"|"present"|"future", "dates": [...]}
    quantities: list[dict] # [{"value": 5, "unit": "km"}]
    actionable: bool       # False for past-tense, emotions, facts

class ExtractedNode:
    content: str           # "Buy milk"
    node_type: str         # Default "memory". Also: "person", "system_status"
    metadata: NodeMetadata

class EdgeMetadata:
    date: str | None       # ISO8601 for HAS_DEADLINE
    value: float | None    # Numeric for TRACKS_METRIC
    unit: str | None
    logged_at: str | None  # When the metric event happened
    deadline_type: str | None  # hard, soft, routine

class ExtractedEdge:
    source_content: str
    target_content: str
    edge_type: str     # HAS_DEADLINE, IS_STATUS, RELATES_TO, TRACKS_METRIC, EXPERIENCED_DURING, DEPENDS_ON, PART_OF
    metadata: EdgeMetadata | None

class ExtractionResult:
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]
```

### Extraction Modes

**Single message** (`process_brain_dump`): Legacy path, still used by `process-message` endpoint.

**Session-level** (`process_session`): Processes full conversation at once. The extraction prompt preamble instructs the LLM to extract the NET STATE — only keep final versions after corrections. Status updates and meta-instructions return empty arrays.

### Nightly Synthesis

**File:** `src/agents/cold_path/synthesis.py`

Runs per-user during the nightly batch job:

1. **Archive DONE items** — Nodes with IS_STATUS→DONE edge older than 7 days: change `node_type` to `archived_{type}` (handles memory, action, concept)
2. **Merge duplicates** — For each node with an embedding, find top-5 similar nodes of same type. If different content, merge: remap all edges from candidate to survivor, delete resulting duplicate edges, delete candidate node. One merge per node per run (conservative).
3. **Edge decay** — All edges with weight > 0.01: multiply by 0.99 (configurable in `graph.yaml`)
4. **Recompute actionable flags** — Nodes with `tense=future` but all temporal dates in the past: update to `actionable=false, tense=past`

## Graph Operations

**File:** `src/core/graph.py`

### Write Operations (event-first)

All write operations follow the same pattern:
1. Append event to `event_stream`
2. Apply mutation to graph projection tables
3. Both in the same session (atomic transaction)

| Function | Event Type | Projection |
|----------|-----------|------------|
| `get_or_create_node()` | `NodeCreated` | INSERT into `graph_nodes` |
| `create_node_event()` | `NodeCreated` | INSERT into `graph_nodes` (always new) |
| `upsert_edge()` | `EdgeAdded` or `EdgeUpdated` | INSERT or UPDATE `graph_edges` |
| `update_status_event()` | `StatusUpdated` | DELETE old IS_STATUS edges, INSERT new |
| `update_content_event()` | `ContentUpdated` | UPDATE `graph_nodes.content` |
| `archive_node_event()` | `NodeArchived` | UPDATE `graph_nodes.node_type` |
| `delete_node_event()` | `NodeDeleted` | DELETE edges + node |
| `remove_edge_event()` | `EdgeRemoved` | DELETE edge |

### Read Operations

| Function | What it Does |
|----------|-------------|
| `search_nodes_semantic()` | pgvector cosine distance search with optional node_type filter |
| `search_nodes_by_edge_structure()` | Find nodes by edge type and/or node type |
| `get_node_neighborhood()` | BFS traversal up to N hops from a node |
| `get_nodes_by_ids()` | Batch fetch by UUID list |
| `get_edges_for_nodes()` | All edges touching a set of nodes |
