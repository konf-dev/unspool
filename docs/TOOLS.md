# Tool Registry

Tools are Python async functions registered with `@register_tool("name")`. The orchestrator calls them from pipeline steps via `tool_call` type. All tools live in `backend/src/tools/`.

**All tools read thresholds and configuration from `config/scoring.yaml`** — no business logic is hardcoded in Python. See [scoring.yaml sections](#configuration) below.

---

## Context Tools (`context_tools.py`)

Used by the context assembler to load data before pipeline execution.

| Tool | Signature | Returns |
|------|-----------|---------|
| `fetch_messages` | `(user_id, limit=20)` | `list[dict]` — recent messages, newest first |
| `fetch_profile` | `(user_id)` | `dict` — user profile fields |
| `fetch_items` | `(user_id)` | `list[dict]` — all open items, sorted by urgency |
| `fetch_urgent_items` | `(user_id, hours=48)` | `list[dict]` — items with deadlines within N hours |
| `fetch_memories` | `(user_id, embedding=None, limit=5)` | `list[dict]` — semantic search if embedding provided, otherwise recent |
| `fetch_entities` | `(user_id)` | `list[dict]` — known entities, sorted by last mentioned |
| `fetch_calendar_events` | `(user_id)` | `list[dict]` — upcoming events from Google Calendar |

## DB Tools (`db_tools.py`)

Core data operations used in pipeline steps.

| Tool | Signature | Returns |
|------|-----------|---------|
| `generate_embedding` | `(text)` | `list[float]` — 1536-dim embedding via OpenAI |
| `save_items` | `(user_id, items, source_message_id=None)` | `list[dict]` — saved items with IDs |
| `search_semantic` | `(user_id, embedding, limit=5)` | `list[dict]` — items by vector similarity |
| `search_hybrid` | `(user_id, embedding, query_text, limit=5)` | `list[dict]` — items by combined vector + text score |
| `search_text` | `(user_id, query_text, limit=5)` | `list[dict]` — items by full-text match |
| `mark_item_done` | `(item, user_id)` | `dict` — updated item |

`search_hybrid` uses `COALESCE` to handle items without embeddings — items with only text matches are still returned with a text-only score, rather than being excluded.

`save_items` accepts either a list of item dicts or a dict with an `items` key. Each item dict can contain: `raw_text`, `interpreted_action`, `deadline_type`, `deadline_at`, `urgency_score`, `energy_estimate`, `entity_ids`.

## Scoring Tools (`scoring_tools.py`)

Urgency and energy estimation. **All thresholds from `config/scoring.yaml`.**

| Tool | Signature | Returns | Config section |
|------|-----------|---------|----------------|
| `calculate_urgency` | `(item, hours_until_deadline=None)` | `float` — 0.0–1.0 urgency score | `urgency_weights`, `urgency_breakpoints`, `deadline_type_scores` |
| `infer_energy` | `(text)` | `str` — `low`, `medium`, or `high` | `energy_levels.*.patterns` |
| `enrich_items` | `(items)` | `list[dict]` — items with `urgency_score` and `energy_estimate` filled in | — |

## Item Matching Tools (`item_matching.py`)

Fuzzy matching for "done" and "skip" intents. **Thresholds from `config/scoring.yaml`.**

| Tool | Signature | Returns | Config section |
|------|-----------|---------|----------------|
| `fuzzy_match_item` | `(user_id, text)` | `dict \| None` — best matching open item, or None | `matching.min_similarity`, `matching.substring_boost` |
| `reschedule_item` | `(item, user_id)` | `dict \| None` — rescheduled item with new nudge_after | `reschedule.urgency_decay_factor`, `reschedule.nudge_delay` |

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

---

## Configuration

All tool thresholds live in `config/scoring.yaml`. Key sections:

| Section | Controls |
|---------|----------|
| `urgency_weights` | Weight of deadline, explicit, recency, dependency factors |
| `urgency_breakpoints` | Score at overdue / 24h / 48h / distant thresholds |
| `deadline_type_scores` | Bonus for hard vs soft deadline types |
| `decay` | Soft decay factor, auto-expire days/threshold, hard ramp formula |
| `energy_levels` | Pattern words for low/medium/high energy classification |
| `momentum` | Lookback window and "on a roll" threshold |
| `pick_next` | Scoring boosts for deadline type, energy, surfacing |
| `reschedule` | Urgency decay factor and per-type nudge delays |
| `matching` | Fuzzy match minimum similarity and substring boost |
| `notifications` | Quiet hours, deadline window, push title/body templates |

---

## Adding a New Tool

1. Create or edit a file in `backend/src/tools/`
2. Decorate with `@register_tool("tool_name")`
3. Import the module in `backend/src/main.py`'s `lifespan()` function
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
