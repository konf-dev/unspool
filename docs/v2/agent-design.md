# Agent Design

## Hot Path — Conversational Agent

**File:** `src/agents/hot_path/graph.py`
**Framework:** LangGraph StateGraph
**Model:** Gemini 2.5 Flash (configurable via `CHAT_MODEL` env var)
**Provider:** Configurable via `CHAT_PROVIDER` env var
**Temperature:** 0.7
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

#### `query_graph(semantic_query, edge_type_filter?, node_type?)`

Searches the user's knowledge graph. Returns nodes with their edges.

- Generates embedding via `gemini-embedding-001` (768d, L2-normalized, task_type=RETRIEVAL_QUERY)
- pgvector cosine distance search, limit 8
- Optional edge_type_filter: only returns nodes that have outgoing edges of that type
- Optional node_type filter: `action`, `concept`, `person`, etc.
- Returns up to 3 immediate edges per node for context

**Response shape:**
```json
[
  {
    "id": "uuid",
    "content": "Buy groceries",
    "type": "action",
    "edges": [
      {"type": "IS_STATUS", "target": "OPEN", "metadata": {}},
      {"type": "HAS_DEADLINE", "target": "Buy groceries", "metadata": {"date": "2026-03-25"}}
    ]
  }
]
```

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

### Context Assembly

**File:** `src/agents/hot_path/context.py`

`assemble_context()` runs 4 loaders in parallel via `asyncio.gather()`:

1. **Profile** — User preferences from `user_profiles` table
2. **Recent Messages** — Last 20 messages from `vw_messages` view (reversed to chronological)
3. **Graph Context** — Embeds the user's message → semantic search (top 10) → neighborhood expansion (1 hop for top 3) → serialized as bullet list
4. **Deadlines** — Next 72h from `vw_actionable` (top 5)

Each loader catches its own exceptions — a failure in one doesn't block the others.

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
class ExtractedNode:
    content: str       # "Buy milk"
    node_type: str     # concept, action, metric, person, emotion

class EdgeMetadata:
    date: str | None   # ISO8601 for HAS_DEADLINE
    value: float | None # Numeric for TRACKS_METRIC
    unit: str | None

class ExtractedEdge:
    source_content: str
    target_content: str
    edge_type: str     # HAS_DEADLINE, IS_STATUS, RELATES_TO, TRACKS_METRIC, EXPERIENCED_DURING
    metadata: EdgeMetadata | None

class ExtractionResult:
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]
```

### Nightly Synthesis

**File:** `src/agents/cold_path/synthesis.py`

Runs per-user during the nightly batch job:

1. **Archive DONE items** — Nodes with IS_STATUS→DONE edge older than 7 days: change `node_type` to `archived_action`
2. **Merge duplicates** — For each node with an embedding, find top-5 similar nodes of same type. If different content, merge: remap all edges from candidate to survivor, delete resulting duplicate edges, delete candidate node. One merge per node per run (conservative).
3. **Edge decay** — All edges with weight > 0.01: multiply by 0.99 (configurable in `graph.yaml`)

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
