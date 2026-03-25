# Graph Memory System

Postgres-native graph memory powering Unspool's context assembly. User messages become nodes connected by typed edges, enabling both semantic search and deterministic structured queries.

## Architecture

```
User message → assemble_context() → [4 parallel loaders] → hierarchical <context> block → LLM
                                     ├── _load_profile()
                                     ├── _load_messages()        (recent 20 messages)
                                     ├── _load_graph()           (semantic search → neighborhood expansion)
                                     └── _load_structured_items() (open items, deadlines, completions)

User message → LLM response → QStash → /jobs/process-message → cold path extractor
                                                                 ├── run_extraction()    (LLM → nodes + edges)
                                                                 ├── semantic dedup      (cosine > 0.9 = same node)
                                                                 └── batch embed + persist
```

## Key Files

```
backend/src/agents/hot_path/
├── context.py        # Context assembly — 4 parallel loaders, hierarchical tiers
├── graph.py          # LangGraph workflow — call_model, call_tools, route_logic
├── tools.py          # query_graph (semantic + structural), mutate_graph
├── state.py          # HotPathState TypedDict
└── system_prompt.py  # Template rendering

backend/src/agents/cold_path/
├── extractor.py      # LLM extraction with semantic dedup + conversation context
├── schemas.py        # ExtractionResult, ExtractedNode, ExtractedEdge
└── synthesis.py      # Nightly synthesis

backend/src/core/
├── graph.py          # DB operations — search_nodes_semantic, search_nodes_by_edge_structure,
│                     #   get_node_neighborhood, upsert_edge, update_status_event, etc.
└── models.py         # SQLAlchemy models — GraphNode, GraphEdge

backend/prompts/
└── agent_system.md   # System prompt with intent routing, emotional calibration
```

## Database Tables

### graph_nodes
- `id` UUID PK, `user_id` UUID FK, `content` TEXT, `node_type` TEXT
- `embedding` vector(768) — Gemini text-embedding-004
- `created_at`, `updated_at` timestamps
- Index: `idx_graph_nodes_user_type` on (user_id, node_type)

### graph_edges
- `id` UUID PK, `user_id` UUID FK
- `source_node_id`, `target_node_id` UUID FKs
- `edge_type` TEXT, `weight` FLOAT, `metadata_` JSONB
- Index: `idx_graph_edges_source_type` on (source_node_id, edge_type)

### Edge Types
| Type | Meaning | Metadata |
|------|---------|----------|
| IS_STATUS | Node → OPEN/DONE status node | — |
| HAS_DEADLINE | Node → self (deadline info) | `{date, deadline_type}` |
| RELATES_TO | Node → related node | — |
| TRACKS_METRIC | Entry → metric | `{value, unit}` |
| EXPERIENCED_DURING | Entry → emotion | — |
| DEPENDS_ON | Task → prerequisite task | — |
| PART_OF | Subtask → parent task | — |

### Views (migration 00009)
- **vw_actionable** — OPEN action/concept nodes with earliest deadline (ROW_NUMBER dedup)
- **vw_messages** — Chat history projected from event_stream
- **vw_timeline** — Nodes with deadlines
- **vw_metrics** — Metric tracking aggregation

All tables have RLS enabled. Backend connects as postgres role (bypasses RLS).

## Context Assembly (per message, ~200-500ms)

`assemble_context()` runs 4 loaders in parallel via `asyncio.gather`:

### Tier 1: Structured (deterministic)
`_load_structured_items()` uses existing DB queries — no LLM calls:
- `get_plate_items()` → all OPEN action items via vw_actionable
- `get_proactive_items(hours=48)` → imminent deadlines
- `get_recently_done_count(hours=48)` → momentum signal

### Tier 2: Semantic (graph search)
`_load_graph()`:
1. Embed user message via Gemini (`RETRIEVAL_QUERY` task type)
2. `search_nodes_semantic()` — pgvector cosine distance, top 10
3. Parallel neighborhood expansion (1-hop, separate sessions per gather)
4. Deduplicate edges from overlapping neighborhoods
5. Linearize to human-readable format: `- buy groceries — status: open, due: 2026-03-28`

### Tier 3: Temporal (conversation continuity)
`_extract_recent_mentions()` — last 3 user messages not yet in graph (cold path delay)

### Output
```xml
<context>
Open items (3):
  - buy groceries — due: 2026-03-28
  - finish report
  - call dentist

Due soon:
  - buy groceries (due: 2026-03-28)

Recently completed: 2 items in the last 48h.

Related memories:
- thesis defense — status: open, due: 2026-04-15
- Mom's birthday — related: gift ideas

Just mentioned:
  - my car registration expires next month
</context>
```

## Tool System

### query_graph
`semantic_query` is **optional**. Three modes:
1. **Semantic**: `semantic_query="thesis"` → embedding search
2. **Structural**: `edge_type_filter="IS_STATUS", node_type="action"` → SQL only (no embedding API call, ~200ms faster)
3. **Combined**: semantic search + edge type post-filter

Empty results return a helpful message: "Nothing matching that search. You have N items tracked."

Output uses humanized descriptions (not raw edge types):
```json
{"id": "...", "item": "buy groceries", "kind": "action", "details": "status: open, due: 2026-03-28"}
```

### mutate_graph
Actions: SET_STATUS, ADD_EDGE, REMOVE_EDGE, UPDATE_CONTENT, ARCHIVE.
Requires node_id from prior query_graph call.

## Cold Path Extraction

`process_brain_dump()` runs async via QStash after each message:

1. Idempotency check (SHA256 hash of user_id + message)
2. LLM extraction (Gemini, temperature=0, structured JSON output)
3. Semantic dedup — cosine distance < 0.1 = existing node reused
4. Batch embedding for new nodes
5. Edge creation via upsert

### Extraction features
- Implicit tasks: "car registration expires next month" → action node with deadline
- Emotional boundaries: venting → emotion node only, no action items
- Dependency tracking: "finish report before presentation" → DEPENDS_ON edge
- Conversation context: last 3 user messages passed for anaphora resolution ("that thing about Sarah")

## System Prompt

Temperature: **0.4** (reduced from 0.7 to limit personality variance)

Intent routing: CAPTURE, QUERY_NEXT, QUERY_SEARCH, QUERY_UPCOMING, STATUS_UPDATE, EMOTIONAL, CONVERSATION

Key instruction: "Your context already contains your open items, upcoming deadlines, and recent completions. Use your context first. Only call query_graph if you need to search for something specific."

Safety deny-list: Never output UUIDs, node IDs, edge types, tool names, or graph internals.

## Graceful Degradation

| Failure | Behavior |
|---------|----------|
| Structured query fails | Error logged, context assembled without structured tier |
| Embedding API fails | Graph context skipped, structured + temporal tiers still work |
| Cold path extraction fails | Warning logged, graph misses this message (next message catches up) |
| Graph empty (new user) | All tiers return empty, agent responds naturally from conversation |
| Neighborhood expansion fails | Nodes returned without edge details |

## Migrations

| Migration | What |
|-----------|------|
| 00001 | Core schema (event_stream, graph_nodes, graph_edges) |
| 00006 | Graph views (vw_actionable, vw_messages, vw_timeline, vw_metrics) |
| 00007 | Gemini embeddings (vector(768) column) |
| 00008 | Fix vw_actionable dedup (DISTINCT ON) |
| 00009 | ROW_NUMBER fix for vw_actionable, ORDER BY removed from views, composite indexes |
