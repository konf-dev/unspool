# Database Design

PostgreSQL via Supabase with pgvector extension for semantic search.

## Tables

### Core (Migration 00001)

#### `event_stream`
Immutable append-only event log. Single source of truth for all mutations.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID NOT NULL | Indexed |
| event_type | TEXT NOT NULL | e.g. `MessageReceived`, `NodeCreated`, `StatusUpdated` |
| payload | JSONB NOT NULL | Event-specific data |
| created_at | TIMESTAMPTZ | |

**Indexes:** `(user_id, created_at DESC)`

**Event Types:**
- `MessageReceived` — payload: `{content, metadata: {trace_id, session_id}}`
- `AgentReplied` — payload: `{content, metadata: {trace_id, session_id}}`
- `NodeCreated` — payload: `{node_id, content, node_type}`
- `EdgeAdded` — payload: `{edge_id, source_id, target_id, edge_type, metadata}`
- `EdgeUpdated` — payload: same as EdgeAdded
- `EdgeRemoved` — payload: `{edge_id, source_id, target_id, edge_type}`
- `StatusUpdated` — payload: `{node_id, new_status}`
- `ContentUpdated` — payload: `{node_id, old_content, new_content}`
- `NodeArchived` — payload: `{node_id, content}`
- `NodeDeleted` — payload: `{node_id, content}`
- `NodesMerged` — payload: `{kept_id, removed_id, kept_content, removed_content}`
- `ColdPathProcessed` — payload: `{idempotency_key, nodes, edges}`

#### `graph_nodes`
Entity/concept nodes in the knowledge graph. Downstream projection from events.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID NOT NULL | |
| content | TEXT NOT NULL | e.g. "Buy milk", "Thesis", "Mom" |
| node_type | TEXT NOT NULL | `concept`, `action`, `metric`, `person`, `emotion`, `system_status`, `archived_action` |
| embedding | vector(768) | Gemini gemini-embedding-001 (L2-normalized) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-updated via trigger |

**Indexes:** HNSW on embedding (cosine), user_id, node_type

#### `graph_edges`
Typed relationships between nodes. Downstream projection from events.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID NOT NULL | |
| source_node_id | UUID FK → graph_nodes | CASCADE delete |
| target_node_id | UUID FK → graph_nodes | CASCADE delete |
| edge_type | TEXT NOT NULL | `HAS_DEADLINE`, `IS_STATUS`, `RELATES_TO`, `TRACKS_METRIC`, `EXPERIENCED_DURING` |
| weight | FLOAT default 1.0 | Decays nightly by 0.99 |
| metadata | JSONB | e.g. `{"date": "2026-03-28T00:00:00Z"}` for deadlines |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-updated via trigger |

**Unique:** `(source_node_id, target_node_id, edge_type)`

### User Profiles (Migration 00002)

#### `user_profiles`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | FK → auth.users |
| display_name | TEXT | |
| timezone | TEXT default 'UTC' | |
| tone_preference | TEXT default 'casual' | casual, neutral, warm |
| length_preference | TEXT default 'medium' | terse, medium, detailed |
| pushiness_preference | TEXT default 'gentle' | gentle, moderate, firm |
| uses_emoji | BOOLEAN default false | |
| primary_language | TEXT default 'en' | ISO 639-1 |
| patterns | JSONB default {} | Detected behavioral patterns |
| last_interaction_at | TIMESTAMPTZ | |
| last_proactive_at | TIMESTAMPTZ | 6h cooldown tracking |
| notification_sent_today | BOOLEAN default false | Reset nightly |
| feed_token | TEXT | Random 32-byte hex for ICS feed URL |
| email_alias | TEXT UNIQUE | For email forwarding |
| created_at | TIMESTAMPTZ | |

**Auto-created** via Supabase trigger `on_auth_user_created` on `auth.users` INSERT.

### Subscriptions & Push (Migration 00003)

#### `subscriptions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID UNIQUE | FK → auth.users |
| tier | TEXT default 'free' | free, paid |
| stripe_customer_id | TEXT | |
| stripe_subscription_id | TEXT | |
| status | TEXT default 'active' | active, cancelled, past_due |
| current_period_end | TIMESTAMPTZ | |
| created_at, updated_at | TIMESTAMPTZ | |

#### `push_subscriptions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID | FK → auth.users |
| endpoint | TEXT NOT NULL | Web Push endpoint URL |
| p256dh | TEXT NOT NULL | |
| auth_key | TEXT NOT NULL | |
| created_at | TIMESTAMPTZ | |

**Unique:** `(user_id, endpoint)`

### Proactive & Scheduled (Migration 00004)

#### `proactive_messages`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID | |
| trigger_type | TEXT NOT NULL | e.g. deadline_imminent, welcome_back |
| content | TEXT NOT NULL | Generated message text |
| priority | INTEGER default 5 | Lower = higher priority |
| status | TEXT default 'pending' | pending, delivered |
| expires_at | TIMESTAMPTZ | 7 days after creation |
| delivered_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

#### `scheduled_actions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID | |
| action_type | TEXT NOT NULL | nudge, check_in, ask_question, surface_item |
| payload | JSONB | e.g. `{"message": "How's the thesis going?"}` |
| run_at | TIMESTAMPTZ NOT NULL | |
| rrule | TEXT | RFC 5545 recurrence rule |
| status | TEXT default 'pending' | pending, executing, executed, failed |
| qstash_message_id | TEXT | For tracking QStash dispatch |
| created_at | TIMESTAMPTZ | |

### Operational (Migration 00005)

#### `error_log`
No RLS — admin access only.

| Column | Type |
|--------|------|
| id | UUID PK |
| trace_id | TEXT |
| user_id | TEXT |
| source | TEXT NOT NULL |
| error_type | TEXT NOT NULL |
| error_message | TEXT |
| stacktrace | TEXT |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |

#### `llm_usage`
No RLS — admin access only.

| Column | Type |
|--------|------|
| id | UUID PK |
| trace_id | TEXT |
| user_id | TEXT |
| pipeline | TEXT NOT NULL |
| model | TEXT NOT NULL |
| input_tokens | INTEGER |
| output_tokens | INTEGER |
| latency_ms | INTEGER |
| created_at | TIMESTAMPTZ |

### Views (Migration 00006)

#### `vw_messages`
Projects `MessageReceived`/`AgentReplied` events into chat history shape.
```sql
SELECT id, user_id, role, content, metadata, created_at FROM vw_messages
```

#### `vw_actionable`
OPEN action nodes with optional deadlines.
```sql
SELECT node_id, user_id, content, node_type, deadline, deadline_type FROM vw_actionable
```

#### `vw_timeline`
All nodes with `HAS_DEADLINE` edges, ordered by deadline date.

#### `vw_metrics`
`TRACKS_METRIC` edge aggregation — metric name, entry content, value, unit, logged_at.

## Row Level Security

All user-facing tables have RLS enabled. Policies enforce `auth.uid() = user_id` (or `= id` for profiles). Operational tables (`error_log`, `llm_usage`) have no RLS — accessed only via admin endpoints using the service key.

### Migration Tracking (Migration 00011)

#### `schema_migrations`

Tracks which database migrations have been applied, with checksums for drift detection.

| Column | Type | Notes |
|--------|------|-------|
| version | TEXT PK | e.g. `00010_graph_node_unique_constraint` |
| applied_at | TIMESTAMPTZ | When the migration was applied |
| checksum | TEXT | SHA-256 of the `.sql` file (NULL for backfilled entries) |
| applied_by | TEXT | `current_user` at time of application |

No RLS — accessed only by the migration runner script (`scripts/migrate.sh`).

### Additional Migrations

| Migration | Purpose |
|-----------|---------|
| 00008 | Fix duplicate items in `vw_actionable` view |
| 00009 | Composite indexes on `(user_id, node_type)`, optimized view queries |
| 00010 | Unique constraint on `graph_nodes(user_id, content, node_type)` |

## SQLAlchemy Models

10 ORM models in `src/core/models.py`:
`EventStream`, `GraphNode`, `GraphEdge`, `UserProfile`, `Subscription`, `PushSubscription`, `ProactiveMessage`, `ScheduledAction`, `ErrorLog`, `LLMUsage`

Connection uses Supavisor-compatible settings (`statement_cache_size=0`), pool size 10 + 20 overflow.
