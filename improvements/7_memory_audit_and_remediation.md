# Unspool Memory System — Full Audit & Remediation Document

## Verification Status: ALL ISSUES CONFIRMED (2026-04-03)

All claims verified against actual source code by 3 parallel exploration agents. Every line number, code snippet, and behavior described below has been confirmed accurate.

---

## Why This Document Exists

User reported: "I asked about how much spending I did last month, the context assembled didn't have all the information about all the times I had mentioned spending something."

Investigation revealed this is not one bug — it's a systemic pattern of **scattered hardcoded limits, silent data loss paths, and retrieval gaps** throughout the backend. This document is a complete inventory of every issue found, what causes it, what the fix is, what the system would look like after, and what changes.

**No backward compatibility constraints** — only test users exist. Schema changes, API changes, behavior changes are all acceptable if they make a better system.

---

## The Two Requirements Being Violated

1. **When user says something, Unspool memorizes it and stores it** — VIOLATED by storage holes (dedup merging distinct entries, edge upsert overwriting metric data, session extraction losing individual events)
2. **When user recalls something, ALL related things surface** — VIOLATED by retrieval holes (DISTINCT ON returning one value, limit=8 cap, system prompt discouraging search, metrics excluded from structured context)

---

## SECTION 1: COMPLETE ISSUE INVENTORY

### CATEGORY A: STORAGE — Data Loss Between User Input and Graph

---

#### A1. Edge Upsert Overwrites Metric Data

**Where:** `backend/src/core/graph.py:101-107`

**What happens now:**
```python
# upsert_edge matches on (source_node_id, target_node_id, edge_type)
stmt = select(GraphEdge).where(
    GraphEdge.source_node_id == source_id,
    GraphEdge.target_node_id == target_id,
    GraphEdge.edge_type == edge_type,
)
# If found → UPDATE metadata. If not → INSERT.
```

User says "spent $50 on groceries" → cold path creates:
- Node: "spent $50 on groceries"
- Edge: TRACKS_METRIC → "spending" node, metadata: `{value: 50, unit: "USD", logged_at: "2026-03-20T10:00:00Z"}`

User says "spent $30 on groceries" → cold path:
- Semantic dedup finds "spent $50 on groceries" (>90% similar) → **reuses same node**
- `upsert_edge` finds existing edge (same source → same target → same edge_type) → **overwrites metadata to `{value: 30}`**
- The $50 entry is gone forever.

**What should happen:**
Each spending event creates a new edge row. The uniqueness should include `logged_at` (server-generated timestamp, not LLM-generated). Two edges from the same source to the same target with different timestamps = two separate data points.

**Fix:** In `_create_nodes_and_edges()`, for TRACKS_METRIC edges: inject `datetime.now(UTC)` as `logged_at` into metadata, then use a new `create_metric_edge()` function that always INSERTs (or use composite key `(source, target, edge_type, logged_at)` for upsert). Since `logged_at` is server-generated and unique per call, this is effectively append-only.

**Result after fix:** Every "spent $X" message creates a distinct edge row. No overwrites. Full spending history preserved.

---

#### A2. Semantic Dedup Merges Distinct Metric Entries

**Where:** `backend/src/agents/cold_path/extractor.py:36, 323-348, 409-427`

**What happens now:**
```python
_DEDUP_MAX_DISTANCE = 0.1  # cosine similarity >= 0.9

# For each extracted node:
existing_node, cached_embedding = await _find_semantic_match(
    session, user_id, enode.content, enode.node_type,
)
if existing_node:
    node_map[enode.content] = existing_node.id  # REUSE existing node
```

"spent $50 on groceries" and "spent $30 on groceries" have ~95% cosine similarity → second entry reuses first node's ID. This is correct for tasks ("buy milk" mentioned twice = same task) but WRONG for metrics (each mention = separate data point).

**What should happen:**
Nodes that represent metric data points should NEVER be deduped. Each "spent $X" should be its own node.

**Fix:** In `_create_nodes_and_edges()`, after extraction, identify nodes that will have TRACKS_METRIC edges. Skip semantic dedup for those nodes — always create new. The dedup check can look ahead at `extraction.edges` to see if the node is a TRACKS_METRIC source.

**Result after fix:** "spent $50 on groceries" and "spent $30 on groceries" become two separate nodes, each with their own TRACKS_METRIC edge. No merging.

---

#### A3. Session Extraction Loses Individual Metric Events

**Where:** `backend/src/agents/cold_path/extractor.py:278-283`

**What happens now:**
```python
session_preamble = (
    "You are reviewing a COMPLETE conversation session. "
    "Extract the NET STATE — what facts, tasks, and information should be remembered..."
    "If something was mentioned then corrected or cancelled, only keep the final version."
)
```

If user says in one session: "spent $50 on groceries", "spent $30 on gas", "spent $20 on coffee" — the LLM may:
- Create one "spending" summary node instead of three separate entries
- Or create three nodes but the "NET STATE" instruction may cause it to consolidate

**What should happen:**
The session extraction instruction should explicitly say: "For metrics and tracked quantities (spending, exercise, measurements), extract EVERY individual entry as a separate node with its own TRACKS_METRIC edge. Do NOT consolidate multiple metric entries into a summary."

**Fix:** Add explicit instruction in `_EXTRACTION_SYSTEM_INSTRUCTION` and `session_preamble`.

**Result after fix:** Session extraction preserves every individual metric entry.

---

#### A4. Nightly Synthesis Merges Metric Nodes

**Where:** `backend/src/agents/cold_path/synthesis.py:93-164`

**What happens now:**
```python
# Nightly at 3 AM: merge nodes with >= 85% similarity
similar = await search_nodes_semantic(
    session, user_id, node.embedding, limit=5, node_type=node.node_type,
    max_distance=0.15,  # LOOSER than cold path dedup (0.1)
)
# If match found: remap all edges from candidate → primary node, delete candidate
```

Even if cold path dedup is fixed (A2), nightly synthesis can still merge spending nodes. "spent $50 on groceries" and "spent $30 on gas" could be 85%+ similar → merged.

**What should happen:**
Nodes that are sources of TRACKS_METRIC edges should be excluded from merge candidates.

**Fix:** In `_merge_duplicates()`, before merging, check if either node is a source of TRACKS_METRIC edges. If so, skip.

**Result after fix:** Metric data points survive nightly synthesis indefinitely.

---

#### A5. Silent Embedding Failures Create Invisible Nodes

**Where:** `backend/src/agents/cold_path/extractor.py:446-447`

**What happens now:**
```python
try:
    embeddings = await get_embeddings_batch(nodes_to_embed, task_type="RETRIEVAL_DOCUMENT")
except Exception:
    logger.warning("cold_path.batch_embed_failed", exc_info=True)
    embeddings = [None] * len(nodes_to_embed)
```

If embedding API fails, nodes are created with `embedding=None`. The semantic search function (`search_nodes_semantic`) filters: `GraphNode.embedding.isnot(None)`. These nodes are permanently invisible to semantic queries.

**What should happen:**
Failed embeddings should be retried. If still failing, nodes should be flagged for later embedding.

**Fix:** Add a `needs_embedding` boolean column or use `embedding IS NULL` as the flag. Add a periodic job that retries embedding for nodes with `embedding=None`. Or: queue a retry with backoff.

**Result after fix:** No nodes are permanently invisible due to transient API failures.

---

#### A6. Cold Path Extraction Failure = Silent Data Loss

**Where:** `backend/src/agents/cold_path/extractor.py:527-534`

**What happens now:**
```python
try:
    extraction = await run_extraction(raw_message, current_time_iso, timezone, recent_messages)
except Exception as e:
    report_error("cold_path.extraction_failed", e, user_id=str(user_id), trace_id=trace_id)
    return  # ← SILENT RETURN. No nodes created. No retry. No user notification.
```

User's message was acknowledged by hot path ("got it, $50 on groceries") but cold path failed → nothing stored in graph.

**What should happen:**
Failed extractions should be queued for retry with exponential backoff. After N failures, flag for manual review or notify.

**Fix:** Instead of `return`, dispatch a retry job via QStash with increasing delay. Add `max_extraction_retries` to config.

**Result after fix:** Transient failures don't cause permanent data loss.

---

#### A7. Content Length Filter Drops Long Messages from Context

**Where:** `backend/src/agents/hot_path/context.py:33`

**What happens now:**
```python
if content and len(content) < 200:
    lines.append(f"  - {content}")
```

Messages longer than 200 characters are excluded from "Just mentioned" context section.

**What should happen:**
Long messages should be truncated, not dropped entirely.

**Fix:** Replace length filter with truncation: `content[:500]` or similar (configurable).

**Result after fix:** All recent messages appear in context, possibly truncated.

---

### CATEGORY B: RETRIEVAL — Data Exists But Doesn't Surface

---

#### B1. `get_metric_summary()` Returns Only Latest Value Per Metric

**Where:** `backend/src/db/queries.py:553-563`

**What happens now:**
```sql
SELECT DISTINCT ON (metric_name)
    metric_name, value AS latest_value, unit, event_time::date::text AS latest_date
FROM vw_metrics
WHERE user_id = :uid
ORDER BY metric_name, event_time DESC
```

If user tracked spending 10 times last month, context shows only: `"Tracking: spending: $30 USD (2026-03-28)"` — the SINGLE most recent entry.

**What should happen:**
The context should show metric history: count, total/sum, recent entries, date range.

**Fix:** Replace with a query that returns:
- Per metric: count, sum, min, max, latest value, date range
- Optionally: last N individual entries
- Add `date_from`/`date_to` parameters for time-scoped queries

New function: `get_metric_history(user_id, metric_name=None, date_from=None, date_to=None, limit=None)`

**Result after fix:** Context shows: `"Tracking: spending: 10 entries (Mar 1-28), total $430 USD, latest $30 (Mar 28)"`

---

#### B2. System Prompt Tells LLM Not To Search

**Where:** `backend/prompts/agent_system.md:64`

**What happens now:**
```
Your context already contains your open items, upcoming deadlines, and recent completions.
For "what should I do?" or "what's on my plate?" — use your context first.
Only call query_graph if you need to search for something specific that isn't in your context
```

LLM sees one spending entry in context → thinks it has the full picture → answers with incomplete data.

**What should happen:**
System prompt should explicitly instruct: for historical/aggregate questions ("how much did I spend?", "show me all my...", "what did I say about..."), ALWAYS call query_graph. Context shows a summary, not the full picture.

**Fix:** Add to system prompt:
```
QUERY_SEARCH and aggregate questions ("how much total", "show me all", "everything about"):
  → ALWAYS call query_graph. Your context shows a summary, not all data.
  → For metrics (spending, exercise, etc.): use edge_type_filter="TRACKS_METRIC" with date range.
  → Request enough results to answer comprehensively.
```

**Result after fix:** LLM reliably searches the graph for historical/aggregate queries.

---

#### B3. query_graph Semantic Search: limit=8

**Where:** `backend/src/agents/hot_path/tools.py:125`

**What happens now:**
```python
nodes = await search_nodes_semantic(
    session, user_uuid, embedding, limit=8, node_type=node_type,
)
```

Hard cap of 8 results regardless of how many matches exist.

**What should happen:**
This should be a configurable hyperparameter, not hardcoded. Ideally, the LLM could request more results via a `limit` parameter on the tool.

**Fix:** Read from `hyperparams.yaml`. Expose as optional `limit` parameter on query_graph tool with a safety cap from config.

**Result after fix:** Default limit is configurable. LLM can request more when needed. Safety cap prevents runaway queries.

---

#### B4. query_graph Structural Search: limit=20

**Where:** `backend/src/core/graph.py:340`

Same pattern as B3 but for structural queries. Hardcoded to 20.

**Fix:** Same — config + optional tool parameter.

---

#### B5. Edge Display: Only 5 Per Node

**Where:** `backend/src/agents/hot_path/tools.py:190`

**What happens now:**
```python
for e in node_edges[:5]:  # Only show first 5 edges
```

If a metric node ("spending") has 20 TRACKS_METRIC edges (20 spending entries), only 5 are shown to the LLM.

**What should happen:**
Configurable, and for metric queries the LLM should be able to see all edges.

**Fix:** Config-driven. Consider a `detail_level` parameter: "summary" (5 edges), "full" (all edges).

---

#### B6. Edge Fetch: Only 20 Per Node

**Where:** `backend/src/agents/hot_path/tools.py:154`

```python
edge_stmt = select(GraphEdge).where(...).limit(20)
```

Even if we fix B5 to show all edges, only 20 are fetched from DB.

**Fix:** Config-driven limit, or remove when detail_level="full".

---

#### B7. Message History to LLM: 10 Messages

**Where:** `backend/src/api/chat.py:102`

```python
recent_messages[-10:]
```

If user mentioned spending in message 15 of the current session, the LLM doesn't see it in conversation history.

**Fix:** Config-driven.

---

#### B8. Plate Items: Max 7

**Where:** `backend/src/db/queries.py:474` — `LIMIT 7`

Only 7 open items shown on "Your plate". User with 15 open items sees 8 hidden.

**Fix:** Config-driven.

---

#### B9. Slipped Items: Max 10

**Where:** `backend/src/db/queries.py:505` — `LIMIT 10`

Only 10 overdue items shown. Others hidden.

**Fix:** Config-driven.

---

#### B10. Graph Walk Hops: 1 (And Never Used By Hot Path)

**Where:** `backend/config/graph.yaml:7` and `backend/src/core/graph.py:345-388`

`get_node_neighborhood()` supports N hops but is NEVER called by the hot path tools. query_graph only does flat semantic or structural search, never graph traversal.

**What should happen:**
query_graph should support a `depth` parameter that triggers neighborhood traversal. "What's related to my spending?" could traverse spending → individual entries → categories.

**Fix:** Add optional `depth` parameter to query_graph. When >0, use `get_node_neighborhood()`.

---

#### B11. No Aggregate Queries

**Where:** `backend/src/agents/hot_path/tools.py` — query_graph returns individual nodes only.

User asks "how much total did I spend?" → LLM gets 8 individual entries (max) and must manually sum. If there are 20 entries, the sum is wrong.

**What should happen:**
query_graph should support aggregate operations, or a new `aggregate_metrics` tool should exist.

**Fix:** Either add aggregate capability to query_graph or add a dedicated `get_metrics` tool that returns SUM/COUNT/AVG from vw_metrics with date filtering.

---

#### B12. vw_actionable Permanently Excludes Past-Tense Non-Actionable Nodes

**Where:** `backend/supabase/migrations/00012_v2_views.sql:36-37`

```sql
WHERE actionable = true AND tense != 'past'
```

Spending entries are `actionable: false, tense: past` → they NEVER appear in plate/overdue/calendar. This is correct behavior (spending isn't a task), but it means the ONLY way to surface spending is via query_graph or get_metric_summary.

**Not a bug** — but worth documenting. The metric retrieval path (B1) must be robust since it's the ONLY path for this data.

---

### CATEGORY C: TIMING

---

#### C1. 3-Minute Cold Path Debounce

**Where:** `backend/src/api/chat.py:310,317`

User says "spent $50" → cold path queued with 3-min delay. User immediately asks "how much did I spend?" → spending isn't in graph yet.

The "Just mentioned" section (context.py:27-35) is the only bridge, but it has the 200-char limit (A7) and only shows last 3 messages.

**Fix:** For QUERY_SEARCH intents, consider triggering immediate extraction of pending sessions before assembling context. Or: expand "Just mentioned" to cover all unprocessed messages from current session.

---

### CATEGORY D: CONFIGURATION CHAOS

---

#### D1. Dual Definition: graph.yaml vs Hardcoded

`graph.yaml` defines `semantic_limit: 15` but `tools.py` hardcodes `limit=8`. The config value is never used by the hot path tools. Which one is authoritative?

#### D2. Dedup Threshold Defined Twice

`graph.yaml` has `dedup_threshold: 0.9` (as similarity). `extractor.py` hardcodes `_DEDUP_MAX_DISTANCE = 0.1` (as distance). These are equivalent (1 - 0.9 = 0.1) but the code doesn't read from config.

#### D3. Synthesis Thresholds Not In Config

Archive age (7 days), merge distance (0.15), decay factor (0.99 — IS in config but hardcoded as fallback) — synthesis.py reads some from config but falls back to hardcoded values.

#### D4. Proactive Cooldown Hardcoded

`engine.py:43` — `6 * 3600` (6 hours). Not in any config file.

#### D5. LLM Temperature/Thinking Budget Hardcoded Per Pipeline

- Hot path: temp=0.4, thinking=4096 (`graph.py:45-46`)
- Cold path: temp=0, thinking=8192 (`extractor.py:230`)
- Proactive: temp=0.8, thinking=0 (`engine.py:104-105`)

None of these are in config.

---

## SECTION 2: WHAT THE SYSTEM LOOKS LIKE AFTER ALL FIXES

### Storage: Zero Data Loss Path

1. Every user message → cold path extraction → **every metric entry becomes its own node + its own edge** (no dedup for metrics, no upsert for metric edges)
2. Session extraction explicitly preserves individual metric events (not NET STATE)
3. Nightly synthesis never merges metric nodes
4. Failed embeddings are retried automatically
5. Failed extractions are retried automatically

### Retrieval: Complete Recall

1. Context assembly shows metric **history** (count, total, recent entries), not just latest
2. System prompt instructs LLM to **always search** for historical/aggregate questions
3. query_graph supports configurable limits (default from config, overridable by LLM)
4. query_graph supports graph traversal depth
5. query_graph edge display is configurable
6. All view-based queries (plate, slipped, calendar) have configurable limits

### Configuration: Single Source of Truth

All hyperparameters in `backend/config/hyperparams.yaml`:

```yaml
# ── Retrieval ──
retrieval:
  semantic_search_limit: 15          # default for query_graph semantic path
  structural_search_limit: 25        # default for query_graph structural path
  max_safety_cap: 100                # absolute max results (prevents runaway)
  edge_fetch_limit: 30               # edges loaded per node
  edge_display_limit: 10             # edges shown per node in results
  graph_walk_hops: 2                 # neighborhood traversal depth

# ── Context Assembly ──
context:
  recent_messages_loaded: 20         # messages fetched from event_stream
  recent_messages_to_llm: 15         # messages in conversation history
  recent_mentions_count: 5           # "Just mentioned" entries
  recent_mention_max_chars: 500      # truncation, not filter
  done_count_lookback_hours: 48
  plate_items_limit: 10
  slipped_items_limit: 15
  metric_history_entries: 10         # per-metric recent entries in context
  max_context_tokens: 4000

# ── Extraction (Cold Path) ──
extraction:
  dedup_max_distance: 0.1            # cosine distance (0.1 = 90% similarity)
  skip_dedup_for_edge_types:         # never dedup nodes with these outgoing edges
    - TRACKS_METRIC
  session_debounce_seconds: 180
  max_retries: 3
  retry_base_delay: 1.0
  llm_temperature: 0
  llm_thinking_budget: 8192

# ── Synthesis (Nightly) ──
synthesis:
  archive_done_after_days: 7
  merge_max_distance: 0.15           # cosine distance for duplicate merge
  merge_candidates_limit: 5
  skip_merge_for_edge_types:         # never merge nodes with these edges
    - TRACKS_METRIC
  edge_decay_factor: 0.99
  edge_decay_min: 0.01

# ── Hot Path Agent ──
agent:
  max_iterations: 5
  llm_temperature: 0.4
  llm_thinking_budget: 4096
  pipeline_timeout_seconds: 60

# ── Proactive ──
proactive:
  cooldown_seconds: 21600            # 6 hours
  llm_temperature: 0.8
  llm_thinking_budget: 0

# ── Rate Limiting ──
rate_limit:
  free_daily_messages: 1000

# ── Expiration ──
expiration:
  soft_deadline_grace_hours: 48
  undated_stale_days: 14
  batch_limit: 100

# ── Embedding ──
embedding:
  retry_max_attempts: 3
  retry_backoff_base: 2.0
```

### LLM Tool Interface: Dynamic Control

query_graph gains optional parameters:
```python
@tool
async def query_graph(
    semantic_query: str | None = None,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    # NEW:
    limit: int | None = None,         # override default, capped by max_safety_cap
    include_all_edges: bool = False,   # return full edge details instead of truncated
    depth: int | None = None,          # graph traversal hops (default: 0 = flat search)
) -> list[dict[str, Any]]:
```

---

## SECTION 3: FILES TO MODIFY (Complete List)

| File | What Changes |
|------|-------------|
| `backend/config/hyperparams.yaml` | **NEW** — all hyperparameters centralized |
| `backend/src/core/graph.py` | Add `create_metric_edge()` — insert-only, server timestamp |
| `backend/src/core/config_loader.py` | Verify it loads hyperparams.yaml (should work as-is) |
| `backend/src/db/queries.py` | Fix `get_metric_summary()` → `get_metric_history()`. Replace all `LIMIT N` with config reads. |
| `backend/src/agents/hot_path/tools.py` | Add limit/include_all_edges/depth params to query_graph. Replace hardcoded 8/20/5 with config. |
| `backend/src/agents/hot_path/context.py` | Replace hardcoded limits with config. Improve metric display (history/totals). Fix 200-char filter → truncation. |
| `backend/src/agents/hot_path/graph.py` | Replace hardcoded temp/thinking_budget with config. |
| `backend/src/agents/cold_path/extractor.py` | Skip dedup for metric nodes. Fix session extraction instruction. Replace hardcoded limits with config. Add embedding retry. |
| `backend/src/agents/cold_path/synthesis.py` | Skip merge for metric nodes. Replace hardcoded limits with config. |
| `backend/prompts/agent_system.md` | Rewrite QUERY_SEARCH section. Teach metric querying. Document new tool params. |
| `backend/src/api/chat.py` | Replace hardcoded limits with config. |
| `backend/src/api/feed.py` | Replace hardcoded limits with config. |
| `backend/src/proactive/engine.py` | Replace hardcoded cooldown with config. |
| `backend/src/jobs/expire_items.py` | Replace hardcoded limits with config. |
| `backend/src/jobs/detect_patterns.py` | Replace hardcoded limits with config. |

---

## SECTION 4: VERIFICATION

1. **Storage test:** Send "spent $50 on groceries", "spent $30 on gas", "spent $20 on coffee" → verify 3 separate nodes + 3 separate TRACKS_METRIC edges in DB
2. **Retrieval test:** Ask "how much did I spend?" → verify all 3 entries surface in response
3. **Config audit:** `grep -rn 'limit=' backend/src/` — verify no magic numbers remain, all reference config
4. **Dedup test:** Send "spent $50 on groceries" twice → verify 2 separate nodes (not deduped)
5. **Nightly synthesis test:** Run synthesis → verify metric nodes NOT merged
6. **Embedding failure test:** Mock embedding API failure → verify nodes flagged for retry
7. **Session extraction test:** Send 5 spending messages in one session → verify all 5 extracted individually
8. **query_graph test:** Call with limit=50 → verify returns up to 50 results (or all if fewer)
9. **Aggregate test:** Ask "total spending last month" → verify correct sum across all entries
