# Database Schema

Unspool uses **Supabase Postgres** with **pgvector** for embeddings. All user-facing tables have Row-Level Security (RLS) enabled — every query is scoped to the authenticated user.

Migrations live in `backend/supabase/migrations/`.

---

## Tables

### user_profiles

Created automatically via trigger when a user signs up through Supabase Auth.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | References `auth.users(id)` |
| display_name | TEXT | |
| timezone | TEXT | IANA timezone (e.g. `America/New_York`) |
| tone_preference | TEXT | `casual` (default), `formal`, `brief` |
| length_preference | TEXT | `short`, `medium` (default), `long` |
| pushiness_preference | TEXT | `gentle` (default), `moderate`, `direct` |
| uses_emoji | BOOLEAN | Default `false` — learned from user behavior |
| primary_language | TEXT | Default `en` |
| google_calendar_connected | BOOLEAN | |
| notification_sent_today | BOOLEAN | Reset daily, prevents notification spam |
| last_interaction_at | TIMESTAMPTZ | Updated on each chat message |
| patterns | JSONB | Behavior patterns detected by background job |
| created_at | TIMESTAMPTZ | |

### messages

Every user and assistant message. The chat log.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | → `auth.users` |
| role | TEXT | `user` or `assistant` |
| content | TEXT | |
| created_at | TIMESTAMPTZ | |
| metadata | JSONB | Contains `trace_id`, `session_id`, proactive trigger type |

**Indexes:** `(user_id, created_at DESC)`

### items

Tasks, reminders, ideas — anything the AI extracts from user messages.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | → `auth.users` |
| raw_text | TEXT | Exact text the user said |
| interpreted_action | TEXT | AI's interpretation (e.g. "Buy groceries at Trader Joe's") |
| deadline_type | TEXT | `hard`, `soft`, or `none` |
| deadline_at | TIMESTAMPTZ | |
| urgency_score | FLOAT | 0.0–1.0, decays over time |
| energy_estimate | TEXT | `low`, `medium`, `high` |
| status | TEXT | `open`, `done`, `expired`, `deprioritized` |
| source_message_id | UUID FK | → `messages` — which message created this item |
| entity_ids | UUID[] | References to `entities` table |
| recurrence_id | UUID FK | → `recurrences` |
| created_at | TIMESTAMPTZ | |
| last_surfaced_at | TIMESTAMPTZ | When this item was last shown to the user |
| nudge_after | TIMESTAMPTZ | Don't surface before this time |
| embedding | vector(768) | Gemini `gemini-embedding-001` (L2-normalized) |
| search_text | tsvector | Auto-generated from `raw_text` + `interpreted_action` |

**Indexes:**
- `(user_id, status)` — main query path
- `(user_id, deadline_at) WHERE status = 'open'` — deadline scanner
- HNSW on `embedding` (cosine) — vector similarity
- GIN on `search_text` — full-text search

### item_events

Audit log for item state changes. `user_id` denormalized for RLS.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| item_id | UUID FK | → `items` |
| user_id | UUID FK | → `auth.users` |
| event_type | TEXT | `created`, `surfaced`, `rescheduled`, `snoozed`, `done`, `expired`, `deprioritized` |
| metadata | JSONB | |
| created_at | TIMESTAMPTZ | |

### memories

Facts the AI learns about the user over time (e.g. "user has a dog named Max").

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | → `auth.users` |
| type | TEXT | `semantic` or `episodic` |
| content | TEXT | The fact itself |
| source_message_id | UUID FK | → `messages` |
| confidence | FLOAT | Default 1.0, can decay |
| last_validated_at | TIMESTAMPTZ | |
| superseded_by | UUID FK | → `memories` (self-reference for corrections) |
| embedding | vector(1536) | |
| search_text | tsvector | Auto-generated from `content` |
| created_at | TIMESTAMPTZ | |

**Indexes:** `(user_id, type)`, HNSW on `embedding`, GIN on `search_text`

### entities

People, places, projects mentioned by the user.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| name | TEXT | |
| type | TEXT | `person`, `project`, `place`, `organization` |
| aliases | TEXT[] | Alternative names |
| context | TEXT | Snippet of how they were mentioned |
| emotional_valence | TEXT | Optional sentiment about this entity |
| last_mentioned_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Updated on re-mention |

**Constraints:** `UNIQUE(user_id, name, type)`

### recurrences

Patterns the AI detects (e.g. "user does laundry every Sunday").

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| description | TEXT | |
| rrule | TEXT | iCalendar RRULE format |
| time_of_day | TIME | |
| source | TEXT | `inferred`, `calendar`, `explicit` |
| confidence | FLOAT | |
| last_triggered_at | TIMESTAMPTZ | |
| active | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

### calendar_events

Synced from Google Calendar (read-only).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| google_event_id | TEXT | |
| summary | TEXT | Event title |
| start_at | TIMESTAMPTZ | |
| end_at | TIMESTAMPTZ | |
| location | TEXT | |
| description | TEXT | |
| is_all_day | BOOLEAN | |
| synced_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Constraints:** `UNIQUE(user_id, google_event_id)`

### subscriptions

One row per user. Managed by Stripe webhooks.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | UNIQUE |
| tier | TEXT | `free` or `paid` |
| stripe_customer_id | TEXT | |
| stripe_subscription_id | TEXT | |
| status | TEXT | `active`, `cancelled`, `past_due` |
| current_period_end | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### push_subscriptions

Web Push API subscription data.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| endpoint | TEXT | |
| p256dh | TEXT | |
| auth_key | TEXT | |
| created_at | TIMESTAMPTZ | |

**Constraints:** `UNIQUE(user_id, endpoint)`

### llm_usage

Token usage tracking. **No RLS** — written by service role only.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| trace_id | UUID | Links to a single user request |
| user_id | UUID | |
| step_id | TEXT | Pipeline step that made this call |
| pipeline | TEXT | |
| variant | TEXT | A/B test variant |
| model | TEXT | |
| provider | TEXT | |
| input_tokens | INT | |
| output_tokens | INT | |
| latency_ms | INT | |
| ttft_ms | INT | Time to first token (streaming steps only) |
| config_hash | TEXT | Combined hash of pipeline + prompt versions used |
| created_at | TIMESTAMPTZ | |

### trace_summary (view)

Aggregated view of `llm_usage` for per-request observability.

| Column | Type | Notes |
|--------|------|-------|
| trace_id | UUID | |
| user_id | UUID | |
| pipeline | TEXT | |
| variant | TEXT | |
| config_hash | TEXT | |
| total_input_tokens | INT | Sum across all LLM calls |
| total_output_tokens | INT | |
| total_latency_ms | INT | |
| first_token_ms | INT | Minimum TTFT across calls |
| llm_calls | INT | Count of LLM calls |
| started_at | TIMESTAMPTZ | |
| steps | TEXT[] | Ordered step IDs |

### experiment_assignments

A/B test variant assignments.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| experiment | TEXT | |
| variant | TEXT | |
| assigned_at | TIMESTAMPTZ | |

**Constraints:** `UNIQUE(user_id, experiment)`

### oauth_tokens

Stores refresh tokens for external providers (Google Calendar).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| provider | TEXT | Default `google` |
| refresh_token | TEXT | |
| scopes | TEXT[] | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Constraints:** `UNIQUE(user_id, provider)`

### memory_nodes

Graph memory: atomic facts, tasks, people, dates, feelings extracted from conversations.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | → `auth.users` |
| content | TEXT | Atomic concept (1-4 words typically) |
| node_type | TEXT | Optional type hint |
| embedding | halfvec(1536) | 50% memory vs vector(1536) |
| status | TEXT | `active`, `merged` |
| source_message_id | UUID FK | → `messages` — provenance |
| created_at | TIMESTAMPTZ | |
| last_activated_at | TIMESTAMPTZ | Updated on retrieval |

**Indexes:**
- `(user_id)` — main query path
- `(user_id, last_activated_at DESC)` — recency trigger
- `(user_id, lower(content))` — content dedup lookup
- HNSW on `embedding` (`halfvec_cosine_ops`, m=16, ef_construction=64)

### memory_edges

Graph memory: bi-temporal relationships between nodes. Corrections invalidate old edges (set `valid_until`) rather than deleting them, preserving history.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | → `auth.users` |
| from_node_id | UUID FK | → `memory_nodes` (CASCADE) |
| to_node_id | UUID FK | → `memory_nodes` (CASCADE) |
| relation_type | TEXT | Optional edge label |
| strength | FLOAT | Default 1.0, decays over time |
| valid_from | TIMESTAMPTZ | When this edge became true |
| valid_until | TIMESTAMPTZ | NULL = current; set on invalidation |
| recorded_at | TIMESTAMPTZ | When this edge was created |
| decay_exempt | BOOLEAN | Protects structural edges from decay |
| source_message_id | UUID FK | → `messages` |

**Indexes:** Partial indexes on `(from_node_id)`, `(to_node_id)`, `(user_id)` WHERE `valid_until IS NULL` — only current edges.

### node_neighbors

Materialized cache for O(1) neighbor lookups during graph retrieval. Rebuilt after evolution cycles.

| Column | Type | Notes |
|--------|------|-------|
| edge_id | UUID FK | → `memory_edges` (CASCADE), part of PK |
| node_id | UUID FK | → `memory_nodes` (CASCADE) |
| neighbor_id | UUID FK | → `memory_nodes` (CASCADE) |
| relation_type | TEXT | Copied from edge |
| strength | FLOAT | Copied from edge |
| direction | TEXT | `outgoing` or `incoming`, part of PK |

**Primary key:** `(edge_id, direction)`

---

## Vector Search

Two types of search are available:

### Semantic (vector only)
```sql
SELECT *, embedding <=> $1::vector AS distance
FROM items WHERE user_id = $2 AND embedding IS NOT NULL
ORDER BY embedding <=> $1::vector LIMIT 5
```

### Hybrid (vector + full-text)
Combines cosine similarity (70% weight) with BM25-style text ranking (30% weight):
```sql
SELECT *,
  (0.7 * (1.0 - (embedding <=> $1::vector))) +
  (0.3 * COALESCE(ts_rank(search_text, plainto_tsquery('english', $2)), 0))
  AS hybrid_score
FROM items
WHERE user_id = $3 AND status = 'open'
ORDER BY hybrid_score DESC LIMIT 5
```

### Text only (keyword fallback)
```sql
SELECT *, ts_rank(search_text, plainto_tsquery('english', $1)) AS rank
FROM items WHERE user_id = $2
  AND search_text @@ plainto_tsquery('english', $1)
ORDER BY rank DESC LIMIT 5
```

---

## RLS Policies

Every user-facing table has a single policy: `auth.uid() = user_id` (or `= id` for `user_profiles`). This means:

- Frontend Supabase SDK calls are scoped automatically
- Backend uses `DATABASE_URL` with the service role (bypasses RLS) but manually scopes all queries by `user_id` from the JWT

---

## Auto-creation

A Postgres trigger creates a `user_profiles` row when a new user signs up:

```sql
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```
