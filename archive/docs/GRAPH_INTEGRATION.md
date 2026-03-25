# Graph Memory Integration — Plan & Architecture

## Status: PLANNING (not yet implemented)

This document describes exactly how the graph memory experiment (`graph_lab_sql/`) integrates into the production backend (`backend/`). No code should be written until this plan is reviewed and approved.

---

## 1. What Exists Today

### Production Pipeline Flow (per user message)

```
User message
    ↓
1. classify_intent()          → intent name + pipeline name
    ↓
2. assemble_context()         → Context object with loaded fields
    ↓
3. execute_pipeline()         → YAML steps: LLM calls + tool calls
    ↓
4. Stream response to user    → SSE tokens
    ↓
5. Save assistant message     → messages table
    ↓
6. Dispatch post-processing   → QStash → /jobs/process-conversation
```

### Context Assembly (context.py)

The `assemble_context()` function loads data fields based on `context_rules.yaml`:

```yaml
# Which fields each intent needs
brain_dump:
  load: [profile, recent_messages]
  optional: [entities]

query_next:
  load: [profile, open_items, urgent_items, recent_messages]
  optional: [calendar_events, memories]
```

Each field has a **loader function** registered in `_LOADERS`:

| Field | Loader | Source |
|-------|--------|--------|
| `profile` | `fetch_profile()` | `user_profiles` table |
| `recent_messages` | `fetch_messages()` | `messages` table |
| `open_items` | `fetch_items()` | `items` table (status=open) |
| `urgent_items` | `fetch_urgent_items()` | `items` table (deadline soon) |
| `memories` | `fetch_memories()` | `memories` table |
| `entities` | `fetch_entities()` | `entities` table |
| `calendar_events` | `fetch_calendar_events()` | `calendar_events` table |

Fields flow into the Context object → into `_build_prompt_variables()` → into Jinja2 prompt templates.

### Response Generation (engine.py)

Every LLM call gets:
1. **System prompt** = `system.md` rendered with `{{ profile }}` + the step-specific prompt
2. **Conversation** = last 10 messages (chronological) + current user message
3. **Variables** = all non-null Context fields + all prior step results

The system prompt (`prompts/system.md`) defines Unspool's personality. Each pipeline step prompt (e.g., `brain_dump_respond.md`) defines the task-specific instructions. They're concatenated:

```
[system.md rendered with profile]
---
[step prompt rendered with all variables]
```

### Post-Processing (process_conversation.py)

After each chat, a background job:
1. Generates embeddings for new items
2. Extracts entities via regex
3. Extracts semantic memories via LLM

---

## 2. How the Personality Layer Works

This is critical to understand because the graph experiment had its own system prompt, and the production system already has one.

### Current Production Personality

Lives in `backend/prompts/system.md`:
- Warm, casual, supportive friend tone
- Core ADHD rules (one thing at a time, no lists, no backlog)
- User preferences from profile (tone, length, pushiness, emoji, language)
- Prompt injection protection via `<user_input>` tags

### Graph Experiment Personality

Lives in `graph_lab_sql/config/prompts/system.md`:
- Same core personality + ADHD rules
- **Additional graph-aware instructions:**
  - "You receive relevant context between `<context>` tags"
  - "Use this context naturally"
  - "Don't repeat recently surfaced items"
  - "Factor in deadline info without stressing the user"
  - "Use pattern knowledge gently"
  - "Never expose graph structure to the user"
- Emotional awareness section (detect frustration, listen before task-pivoting)
- Profile preferences (same template)

### Integration Decision: Merge System Prompts

The production `system.md` needs the graph-aware instructions added to it. The personality doesn't change — we're adding awareness of a new context source.

**What changes in `system.md`:**
- Add "Handling graph context" section (use `<context>` naturally, don't repeat surfaced items, etc.)
- Add emotional awareness section
- Keep existing personality and rules unchanged

**What does NOT change:**
- The personality itself (warm, casual, friend)
- The ADHD rules (one thing, no lists, no backlog)
- The prompt injection protection
- The profile preferences template
- Per-pipeline prompts (brain_dump_respond.md, etc.) — these don't need to know about the graph

### The "Swappable Final Layer" Principle

From our architecture decisions:

> Everything upstream (intent classification, context assembly, graph retrieval, tool execution) is purely functional. Personality lives only in the final LLM response prompt.

This means:
- `system.md` is the personality layer
- Graph context is a template variable, not a personality change
- Changing `system.md` to a first-person inner-voice prompt should work without touching any graph code
- The graph serialization produces structured text; the personality prompt decides how to present it

**Concretely:** The serialized graph context (`<context>...</context>`) is injected into the prompt variables. The `system.md` instructions tell the LLM how to use it. If you swap `system.md` to an inner-voice version, the same `<context>` block is still there — only the framing changes.

---

## 3. What the Graph Adds

### New Data Flow (additions in **bold**)

```
User message
    ↓
1. classify_intent()
    ↓
2. assemble_context()
   ├── existing loaders (profile, messages, items, etc.)
   └── **graph_context loader (NEW)**
       ├── generate message embedding
       ├── run trigger chain (5 parallel triggers + walk)
       ├── load subgraph (nodes + edges)
       └── serialize to text
    ↓
3. execute_pipeline()  (unchanged — graph_context is just another variable)
    ↓
4. Stream response
    ↓
5. Save message
    ↓
6. Dispatch post-processing
   ├── process_conversation (existing)
   └── **process_graph (NEW)**
       ├── save user message to graph raw_stream
       ├── quick_ingest: extract nodes + edges from message
       ├── detect_feedback: what was surfaced/completed
       └── apply_feedback: update graph state
```

### New Database Tables (3 tables, 1 cache)

**Note:** The experiment had a `raw_stream` table. In production, we skip it — the `messages` table already serves this purpose. Graph nodes link back to messages via `source_message_id`.

```sql
-- memory_nodes: atomic facts, tasks, people, dates, feelings
memory_nodes (id, user_id, content, node_type, embedding, status,
              source_message_id, created_at, last_activated_at)

-- memory_edges: bi-temporal relationships
memory_edges (id, user_id, from_node_id, to_node_id, relation_type,
              strength, valid_from, valid_until, recorded_at,
              decay_exempt, source_message_id)

-- node_neighbors: materialized cache for fast retrieval
node_neighbors (edge_id, node_id, neighbor_id, relation_type,
                strength, direction)
```

### New Backend Modules

```
backend/src/graph/
├── __init__.py
├── types.py          # Node, Edge, TriggerResult, ActiveSubgraph, IngestOutput, etc.
├── db.py             # All graph SQL queries (uses production pool from db.supabase)
├── triggers.py       # 5 trigger functions (vector_search, date_proximity, etc.)
├── retrieval.py      # Trigger chain orchestration → ActiveSubgraph
├── serialization.py  # Subgraph → LLM-readable text with token budget
├── ingest.py         # Node/edge extraction from messages (LLM + corrections)
├── evolve.py         # Background graph evolution (embeddings, dedup, decay)
└── feedback.py       # Post-response graph updates (surfaced, completed)
```

### New Config Files

```
backend/config/graph.yaml       # Graph system settings (ingest, retrieval, evolution)
backend/config/triggers.yaml    # Trigger chain definitions (6 triggers, dependencies)
```

### New Prompts

```
backend/prompts/graph_ingest.md    # Node extraction prompt (from graph_lab_sql)
backend/prompts/graph_evolve.md    # Graph evolution prompt (from graph_lab_sql)
```

### New Job

```
backend/src/jobs/process_graph.py  # Post-processing: ingest + feedback
```

---

## 4. Exactly What Changes in Existing Files

### `backend/src/orchestrator/types.py`

**Add one field to Context:**
```python
class Context(BaseModel):
    # ... existing fields ...
    graph_context: str | None = None   # ← NEW: serialized subgraph text
```

### `backend/src/orchestrator/context.py`

**Add graph_context to the loader registry:**
```python
from src.tools.graph_tools import fetch_graph_context

_LOADERS["graph_context"] = fetch_graph_context
```

### `backend/src/orchestrator/engine.py`

**Add graph_context to `_build_prompt_variables()`:**
```python
if context.graph_context is not None:
    variables["graph_context"] = context.graph_context
```

### `backend/config/context_rules.yaml`

**Add graph_context as optional field for intents that benefit from it:**
```yaml
brain_dump:
  load: [profile, recent_messages]
  optional: [entities, graph_context]     # ← added

query_next:
  load: [profile, open_items, urgent_items, recent_messages]
  optional: [calendar_events, memories, graph_context]  # ← added

query_search:
  load: [profile, recent_messages]
  optional: [graph_context]               # ← added

status_done:
  load: [profile, open_items, recent_messages]
  optional: [graph_context]               # ← added

conversation:
  load: [profile, recent_messages]
  optional: [memories, entities, graph_context]  # ← added

emotional:
  load: [profile, recent_messages]
  optional: [memories, graph_context]     # ← added
```

### `backend/config/jobs.yaml`

**Add process_graph to dispatch map:**
```yaml
dispatch_map:
  process_conversation: process-conversation
  process_graph: process-graph             # ← NEW
```

### `backend/src/jobs/router.py`

**Add process-graph endpoint** (same pattern as process-conversation).

### `backend/src/db/supabase.py`

**Add graph tables to `delete_user_data()`:**
```python
tables_with_user_id = [
    "node_neighbors",      # ← NEW (must be before memory_edges)
    "memory_edges",        # ← NEW (must be before memory_nodes)
    "memory_nodes",        # ← NEW
    "item_events",
    # ... existing tables ...
]
```

**Note:** `node_neighbors` has CASCADE on edge FK, but explicit delete is safer for the delete_user_data flow.

### `backend/src/orchestrator/config_models.py`

**Add config models for graph.yaml and triggers.yaml** (so startup validation catches config errors).

### `backend/prompts/system.md`

**Add graph context handling and emotional awareness** (merge from graph_lab_sql version). See Section 2 above for details.

### Pipeline YAML files that use graph_context

**No changes needed.** The graph context flows through `system.md` (which is prepended to every LLM call). Individual pipeline prompts don't reference `graph_context` directly — the system prompt tells the LLM to use the `<context>` block naturally.

However, to make graph context visible in prompt templates (for future use), it's available as `{{ graph_context }}` in any prompt that needs it.

---

## 5. Key Adaptation Decisions (Experiment → Production)

### Use production pool, not separate pool

The experiment creates its own asyncpg pool. Production's `graph/db.py` calls `supabase.get_pool()` instead. One pool, one connection lifecycle.

### Use production LLM providers

The experiment has its own `llm.py` with Anthropic/OpenAI/Ollama routing. Production's `graph/ingest.py` and `graph/evolve.py` use `get_llm_provider()` from `src.llm.registry` and `get_embedding_provider()` for embeddings.

### Use production prompt renderer

The experiment uses raw Jinja2 Template. Production's graph prompts go in `backend/prompts/` and use `render_prompt()` from `src.orchestrator.prompt_renderer`.

### Use production config loader

The experiment has its own `config.py`. Production's graph config goes in `backend/config/graph.yaml` and `triggers.yaml`, loaded via `load_config()`.

### Skip raw_stream table

The experiment has a `raw_stream` table for message storage. Production already has `messages`. Graph nodes reference messages via `source_message_id UUID REFERENCES messages(id)`.

### Graph context is optional, fail-open

If graph retrieval fails (no nodes yet, DB error, timeout), the response generates normally without graph context. The loader is always listed as `optional` in context_rules.yaml, never `load` (required).

### Shadow mode first

Initial deployment: graph ingest runs in post-processing, graph context is assembled but **logged, not injected into responses**. Compare graph context quality against existing context before going live. This means the context loader has a config flag to control whether the serialized text is actually set on the Context object or just logged.

---

## 6. Data Flow Diagrams

### Request Path (user-facing, latency-sensitive)

```
assemble_context()
    │
    ├── fetch_profile()           ~5ms
    ├── fetch_messages()          ~10ms
    ├── fetch_items()             ~10ms
    │
    └── fetch_graph_context()     ~100-200ms
        │
        ├── generate_embedding()   ~50ms (OpenAI API)
        │
        ├── trigger chain (parallel)
        │   ├── vector_search      ~20ms (pgvector)
        │   ├── date_proximity     ~10ms (SQL CTE)
        │   ├── status_query       ~10ms (neighbor cache)
        │   ├── recency            ~5ms  (SQL)
        │   └── status_query       ~10ms (neighbor cache)
        │
        ├── walk trigger           ~15ms (neighbor cache, sequential)
        │
        ├── load subgraph          ~15ms (batch node/edge fetch)
        │
        └── serialize_subgraph()   ~5ms  (CPU, tiktoken)
```

**Total graph overhead: ~100-200ms.** The existing context assembly is ~25ms. With graph, total context assembly is ~125-225ms. Within budget for real-time chat.

### Post-Processing Path (background, not latency-sensitive)

```
/jobs/process-graph
    │
    ├── quick_ingest()            ~3-4s (LLM call)
    │   ├── LLM extracts nodes + edges from message
    │   ├── Match existing nodes (content search)
    │   ├── Create new nodes
    │   ├── Create edges + populate neighbor cache
    │   └── Apply corrections (invalidate old edges)
    │
    └── detect_feedback()         ~1-2s (LLM call)
        ├── LLM identifies what was surfaced/completed
        └── apply_feedback()
            ├── Mark surfaced nodes
            └── Invalidate "not done" edges for completions
```

### Evolution Job (periodic background, lowest priority)

```
/jobs/evolve-graph (daily or per-session)
    │
    ├── Generate missing embeddings        (batch OpenAI API)
    ├── Discover connections via similarity (pgvector search)
    ├── LLM synthesis (merges, contradictions, refinements)
    ├── Edge decay (multiply strength × 0.99)
    ├── Prune weak edges (invalidate below 0.01)
    └── Rebuild neighbor cache
```

---

## 7. Open Questions

### Q1: When does graph_context get its embedding?

The graph context loader needs the user's current message embedding to run the `vector_search` trigger. Two options:

**Option A:** Generate embedding inside the loader.
- Pro: Self-contained, no changes to existing loaders
- Con: Adds ~50ms to the request path; may duplicate if process_conversation also generates embeddings

**Option B:** Generate embedding once in context assembly, share with all loaders.
- Pro: One API call
- Con: Requires a mechanism to pass computed values between loaders (currently each loader is independent)

**Recommendation:** Option A for now. 50ms is acceptable. Deduplicate later if it becomes a problem.

### Q2: Which pipelines add graph ingest to post-processing?

Currently only `brain_dump.yaml` dispatches `process_conversation`. Should graph ingest run after every message or only brain dumps?

**Recommendation:** Every message. The graph needs to see the full conversation to build connections. The ingest prompt handles casual messages gracefully (returns empty arrays). Add `process_graph` as a second post-processing job on all pipelines that have `post_processing`.

But first: only pipelines that already have `post_processing` get it. New pipelines can be added later.

### Q3: Shadow mode — how to log without injecting?

The graph context loader could:
1. Always build the serialized text
2. Log it with the trace_id
3. Only set `context.graph_context` if a config flag is enabled

```yaml
# graph.yaml
shadow_mode: true   # log graph_context but don't inject into responses
```

When shadow_mode is off, the loader sets the context field normally.

### Q4: How does graph evolution get triggered?

Options:
- **Cron job** (daily) — simple, runs for all active users
- **Post-processing** — after each session (defined by gap > 4h), run evolution
- **Manual** — admin API trigger for testing

**Recommendation:** Start with cron (daily at 3am, same as detect-patterns). Add session-boundary triggering later.

### Q5: How do graph nodes relate to items?

The `items` table and `memory_nodes` table will have overlapping data. A brain dump creates items (structured) AND graph nodes (relational). They're not linked by FK — they coexist as different views of the same information.

**Future:** A `graph_node_id` column on `items` could link them. Not needed for v1.

---

## 8. File-by-File Implementation Checklist

### New Files to Create

| # | File | Lines (est.) | Adapts from | Key changes from experiment |
|---|------|-------------|-------------|---------------------------|
| 1 | `backend/supabase/migrations/00004_graph_memory_tables.sql` | 60 | `graph_lab_sql/src/schema.sql` | Drop raw_stream, use messages FK, add RLS |
| 2 | `backend/src/graph/__init__.py` | 0 | — | Empty package init |
| 3 | `backend/src/graph/types.py` | 130 | `graph_lab_sql/src/types.py` | Drop simulation/config models, keep data + LLM output models |
| 4 | `backend/src/graph/db.py` | 500 | `graph_lab_sql/src/db.py` | Use `supabase.get_pool()`, drop `run_schema()`/`close()`/`get_pool()`, drop raw_stream functions |
| 5 | `backend/src/graph/triggers.py` | 125 | `graph_lab_sql/src/triggers.py` | Import from `src.graph.db`, use production logger |
| 6 | `backend/src/graph/retrieval.py` | 150 | `graph_lab_sql/src/retrieval.py` | Import from `src.graph`, use production logger |
| 7 | `backend/src/graph/serialization.py` | 260 | `graph_lab_sql/src/serialization.py` | Load config via `load_config("graph")`, production logger |
| 8 | `backend/src/graph/ingest.py` | 200 | `graph_lab_sql/src/ingest.py` | Use production LLM provider + prompt renderer |
| 9 | `backend/src/graph/evolve.py` | 170 | `graph_lab_sql/src/evolve.py` | Use production LLM + embedding providers |
| 10 | `backend/src/graph/feedback.py` | 100 | `graph_lab_sql/src/feedback.py` | Use production LLM provider |
| 11 | `backend/config/graph.yaml` | 30 | `graph_lab_sql/config/graph.yaml` | Drop database section, add shadow_mode |
| 12 | `backend/config/triggers.yaml` | 45 | `graph_lab_sql/config/triggers.yaml` | Identical |
| 13 | `backend/prompts/graph_ingest.md` | 140 | `graph_lab_sql/config/prompts/ingest.md` | Identical content |
| 14 | `backend/prompts/graph_evolve.md` | 50 | `graph_lab_sql/config/prompts/evolve.md` | Identical content |
| 15 | `backend/src/tools/graph_tools.py` | 60 | — | New: `fetch_graph_context()` registered as tool |
| 16 | `backend/src/jobs/process_graph.py` | 80 | — | New: calls ingest + feedback |

### Existing Files to Modify

| # | File | Change | Size |
|---|------|--------|------|
| 17 | `backend/src/orchestrator/types.py` | Add `graph_context: str \| None = None` to Context | 1 line |
| 18 | `backend/src/orchestrator/context.py` | Add graph_context to `_LOADERS` | 3 lines |
| 19 | `backend/src/orchestrator/engine.py` | Add graph_context to `_build_prompt_variables()` | 2 lines |
| 20 | `backend/config/context_rules.yaml` | Add graph_context as optional to 6 intents | 6 lines |
| 21 | `backend/config/jobs.yaml` | Add process_graph to dispatch_map | 1 line |
| 22 | `backend/src/jobs/router.py` | Add process-graph route | 15 lines |
| 23 | `backend/src/db/supabase.py` | Add graph tables to delete_user_data | 3 lines |
| 24 | `backend/src/orchestrator/config_models.py` | Add GraphConfig, TriggersConfig to CONFIG_MODELS | 30 lines |
| 25 | `backend/prompts/system.md` | Add graph context handling + emotional awareness | 15 lines |

**Total: 16 new files, 9 modified files. ~1,900 lines of new code.**

---

## 9. Testing Strategy

### Unit Tests (backend/tests/)

| Test file | What it tests |
|-----------|--------------|
| `test_graph_db.py` | All graph SQL functions against test DB |
| `test_graph_triggers.py` | Trigger functions with mocked DB |
| `test_graph_retrieval.py` | Trigger chain orchestration |
| `test_graph_serialization.py` | Subgraph → text conversion |
| `test_graph_ingest.py` | Node extraction with mocked LLM |
| `test_graph_feedback.py` | Surfaced/completion detection |

### Integration Tests

| Test | What it validates |
|------|------------------|
| Graph context in pipeline | Context assembles with graph_context, pipeline renders it |
| Post-processing dispatch | process_graph job runs after chat |
| Shadow mode | graph_context assembled but not injected when shadow_mode=true |
| Delete user data | Graph tables cleared on account deletion |

---

## 10. Deployment Sequence

1. **Merge migration** — adds tables to Supabase (no code changes yet)
2. **Merge graph module + post-processing** — graph ingest starts building graphs in background
3. **Merge context loader (shadow mode)** — graph retrieval runs, results logged but not used
4. **Validate via Langfuse** — compare graph context quality across real conversations
5. **Disable shadow mode** — graph context injected into responses
6. **Add evolution cron** — periodic graph maintenance
