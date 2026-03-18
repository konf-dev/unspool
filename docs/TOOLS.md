# Tool Registry

Tools are Python async functions registered with `@register_tool("name")`. The orchestrator calls them from pipeline steps via `tool_call` type. All tools live in `backend/src/tools/`.

Tool modules are auto-discovered on startup — adding a new file in `src/tools/` with `@register_tool` decorators is sufficient. No need to edit `main.py`.

---

## Context Tools (`context_tools.py`)

Used by the context assembler to load data before pipeline execution.

| Tool | Signature | Returns |
|------|-----------|---------|
| `fetch_messages` | `(user_id, limit=20)` | `list[dict]` — recent messages, newest first |
| `fetch_profile` | `(user_id)` | `dict` — user profile fields |
| `fetch_items` | `(user_id, limit=50)` | `list[dict]` — open items, sorted by urgency |
| `fetch_urgent_items` | `(user_id, hours=48)` | `list[dict]` — items with deadlines within N hours |
| `fetch_memories` | `(user_id, embedding=None, limit=5)` | `list[dict]` — semantic search if embedding provided, otherwise recent |
| `fetch_entities` | `(user_id)` | `list[dict]` — known entities, sorted by last mentioned |
| `fetch_calendar_events` | `(user_id)` | `list[dict]` — upcoming events from Google Calendar |

Context limits (`limit` params) are configured in `config/context_rules.yaml` under `defaults`.

## DB Tools (`db_tools.py`)

Core data operations used in pipeline steps.

| Tool | Signature | Returns |
|------|-----------|---------|
| `generate_embedding` | `(text)` | `list[float]` — 1024-dim embedding via OpenAI |
| `save_items` | `(user_id, items, source_message_id=None)` | `list[dict]` — saved items with IDs |
| `search_semantic` | `(user_id, embedding, limit=5)` | `list[dict]` — items by vector similarity |
| `search_hybrid` | `(user_id, embedding, query_text, limit=5)` | `list[dict]` — items by combined vector + text score |
| `search_text` | `(user_id, query_text, limit=5)` | `list[dict]` — items by full-text match |
| `mark_item_done` | `(item, user_id)` | `dict` — updated item |

`search_hybrid` uses `COALESCE` to handle items without embeddings — items with only text matches are still returned with a text-only score, rather than being excluded.

`save_items` accepts either a list of item dicts or a dict with an `items` key. Each item dict can contain: `raw_text`, `interpreted_action`, `deadline_type`, `deadline_at`, `urgency_score`, `energy_estimate`, `entity_ids`.

## Scoring Tools (`scoring_tools.py`)

Fills in defaults for items where the LLM didn't provide energy or urgency values.

| Tool | Signature | Returns |
|------|-----------|---------|
| `enrich_items` | `(items)` | `list[dict]` — items with `urgency_score` and `energy_estimate` filled in |

`enrich_items` does NOT override LLM-provided values. It only fills defaults:
- `energy_estimate` defaults to `"medium"` if the LLM returned null
- `urgency_score` defaults based on `deadline_type`: hard → 0.5, soft → 0.3, none → 0.1

Energy estimation and urgency scoring are handled by the LLM in the `brain_dump_extract.md` prompt, not by heuristics. The `decay_urgency` cron job maintains urgency scores over time.

## Query Tools (`query_tools.py`)

Dynamic data fetching for complex user queries.

| Tool | Signature | Returns |
|------|-----------|---------|
| `smart_fetch` | `(user_id, query_spec)` | `dict` — results keyed by source (`items`, `memories`, `messages`, `calendar`) |

`smart_fetch` takes a structured `query_spec` dict (produced by the `analyze_query.md` LLM step) and constructs targeted DB queries. Supports:
- **Entity filtering** — resolves entity names to IDs via case-insensitive match against `entities` table
- **Timeframe filtering** — parses `"last_week"`, `"last_month"`, `"last_N_days"` into datetime ranges
- **Multi-source search** — queries any combination of `items`, `memories`, `messages`, `calendar`
- **Status filtering** — `"open"`, `"done"`, or `"all"`
- **Limit capping** — max 100 results per source to prevent excessive fetches

Falls back gracefully if `query_spec` is malformed (e.g. LLM JSON parse failure).

## Item Matching Tools (`item_matching.py`)

Matching for "done" and "skip" intents. **Thresholds from `config/scoring.yaml`.**

| Tool | Signature | Returns | Config section |
|------|-----------|---------|----------------|
| `fuzzy_match_item` | `(user_id, text)` | `dict \| None` — best matching open item, or None | `matching.min_similarity`, `matching.substring_boost` |
| `reschedule_item` | `(item, user_id)` | `dict \| None` — rescheduled item with new nudge_after | `reschedule.urgency_decay_factor`, `reschedule.nudge_delay` |

`fuzzy_match_item` first tries full-text search using the `search_text` tsvector column on `items`. If no results, falls back to word overlap + substring matching.

`reschedule_item` applies different nudge delays based on deadline type:
- `hard` → delay by N hours (default 4)
- `soft` → delay by N days (default 2)
- `none` → delay by N days (default 7)

## Momentum Tools (`momentum_tools.py`)

Track completion streaks for positive reinforcement. **Thresholds from `config/scoring.yaml`.**

| Tool | Signature | Returns | Config section |
|------|-----------|---------|----------------|
| `check_momentum` | `(user_id)` | `dict` — `{done_today: int, on_a_roll: bool}` | `momentum.lookback_hours`, `momentum.on_a_roll_threshold` |
| `pick_next_item` | `(items, user_id)` | `dict \| None` — single best item to surface next | `pick_next.boost_*` values |

`pick_next_item` scores items by combining urgency_score with configurable boosts for deadline type, energy level, and never-surfaced items.

## Graph Tools (`graph_tools.py`)

Graph memory context retrieval. Used by the context assembler (not pipeline steps).

| Tool | Signature | Returns |
|------|-----------|---------|
| `fetch_graph_context` | `(user_id, message="")` | `str \| None` — serialized `<context>` block from graph, or None |

`fetch_graph_context` embeds the user message, runs the trigger chain (semantic, temporal, open_items, recent, suppression, graph_walk), builds an active subgraph, and serializes it into a token-budgeted text block. Returns `None` if graph is empty, tables don't exist, or shadow mode is on.

Configured via `config/graph.yaml` (retrieval, serialization) and `config/triggers.yaml` (trigger chain). Loaded as an optional context field in `config/context_rules.yaml`.

---

## Configuration

Tool thresholds live in `config/scoring.yaml`. Key sections:

| Section | Controls |
|---------|----------|
| `decay` | Soft decay factor, auto-expire days/threshold, hard ramp formula |
| `momentum` | Lookback window and "on a roll" threshold |
| `pick_next` | Scoring boosts for deadline type, energy, surfacing |
| `reschedule` | Urgency decay factor and per-type nudge delays |
| `matching` | Fuzzy match minimum similarity and substring boost |
| `notifications` | Quiet hours, deadline window, push title/body templates |

Additional config files:
- `config/jobs.yaml` — Cron schedules and post-processing dispatch mapping
- `config/patterns.yaml` — Pattern detection analysis definitions (which LLM analyses run, thresholds, prompt templates)
- `config/graph.yaml` — Graph memory: ingest model, retrieval limits, serialization budget, evolution thresholds, shadow mode
- `config/triggers.yaml` — Graph retrieval trigger chain definitions (which triggers run, params, dependencies)

---

## Adding a New Tool

1. Create or edit a file in `backend/src/tools/`
2. Decorate with `@register_tool("tool_name")`
3. Tool is auto-discovered on startup — no need to edit `main.py`
4. Use in a pipeline step:
   ```yaml
   - id: my_step
     type: tool_call
     tool: tool_name
     input:
       arg1: "${context.user_id}"
   ```
5. If the tool needs configurable thresholds, add them to `config/scoring.yaml`
6. Add a test in `backend/tests/test_tool_registry.py`
