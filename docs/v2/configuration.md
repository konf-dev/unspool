# Configuration

## Environment Variables

**File:** `src/core/settings.py` — Pydantic BaseSettings with `.env` file support.

### Provider API Keys

One key per LLM provider. Only set the keys for providers you actually use.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | yes (if using Gemini) | | Google AI Studio key — get from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `OPENAI_API_KEY` | | | OpenAI key — only needed if any pipeline uses OpenAI |
| `ANTHROPIC_API_KEY` | | | Anthropic key — only needed if any pipeline uses Anthropic |

### Per-Pipeline LLM Configuration

Each pipeline declares its provider and model explicitly. To switch a single pipeline to a different provider, change its `*_PROVIDER` and `*_MODEL`, and ensure the corresponding `*_API_KEY` is set.

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_PROVIDER` | `gemini` | Provider for hot path chat |
| `CHAT_MODEL` | `gemini-2.5-flash` | Model for hot path chat |
| `EXTRACTION_PROVIDER` | `gemini` | Provider for cold path graph extraction |
| `EXTRACTION_MODEL` | `gemini-2.5-flash` | Model for cold path extraction |
| `BACKGROUND_PROVIDER` | `gemini` | Provider for proactive messages + pattern detection |
| `BACKGROUND_MODEL` | `gemini-2.5-flash` | Model for background jobs |
| `EMBEDDING_PROVIDER` | `gemini` | Provider for vector embeddings |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Output dimensionality (768, 1536, or 3072 recommended) |

**How key resolution works:** `settings.api_key_for("gemini")` looks up `GOOGLE_API_KEY`. The mapping is: `gemini`/`google` → `GOOGLE_API_KEY`, `openai` → `OPENAI_API_KEY`, `anthropic` → `ANTHROPIC_API_KEY`. No fallbacks — if the key is missing, it raises immediately with a clear error.

### Infrastructure

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | prod | `postgresql+asyncpg://...localhost` | Async PostgreSQL connection string |
| `SUPABASE_URL` | prod | | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | prod | | Supabase service role key |
| `SUPABASE_PUBLISHABLE_KEY` | | | Supabase anon key |
| `SUPABASE_JWT_SIGNING_SECRET` | | | For JWT verification |
| `QSTASH_TOKEN` | | | QStash publish/manage token |
| `QSTASH_URL` | | | Custom base URL (e.g. `https://qstash-eu-central-1.upstash.io` for EU) |
| `QSTASH_CURRENT_SIGNING_KEY` | | | For webhook verification |
| `QSTASH_NEXT_SIGNING_KEY` | | | Key rotation support |
| `UPSTASH_REDIS_REST_URL` | | | Redis for cache + rate limits |
| `UPSTASH_REDIS_REST_TOKEN` | | | |

### App & Auth

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | | `development` | `development` or `production` |
| `FRONTEND_URL` | | `http://localhost:5173` | CORS origin |
| `API_URL` | | `http://localhost:8000` | For QStash URL construction |
| `ADMIN_API_KEY` | | | Admin endpoint access |
| `EVAL_API_KEY` | | | Eval framework access |
| `EMAIL_WEBHOOK_SECRET` | | | HMAC secret for email inbound webhook |
| `CORS_EXTRA_ORIGINS` | | | Comma-separated additional origins |
| `ECHO_SQL` | | `false` | Log all SQL queries |

### Optional Services

| Variable | Description |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe billing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification |
| `VAPID_PRIVATE_KEY` | Web Push VAPID key |
| `VAPID_PUBLIC_KEY` | |
| `LANGFUSE_HOST` | e.g. `https://cloud.langfuse.com` |
| `LANGFUSE_PUBLIC_KEY` | |
| `LANGFUSE_SECRET_KEY` | |

**Production validation:** In non-development environments, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `DATABASE_URL` are required — startup fails if missing.

## YAML Configuration Files

All in `backend/config/`. Loaded via `load_config(name)` with file-mtime caching (auto-reloads in dev, cached in prod). SHA256 hash tracking for change detection.

### `gate.yaml` — Rate Limiting
```yaml
rate_limits:
  free:
    daily_messages: 1000
    message: "You've reached your daily message limit."
  paid:
    daily_messages: -1  # unlimited
```

### `jobs.yaml` — Cron Schedules
```yaml
cron_jobs:
  hourly-maintenance:
    schedule: "0 * * * *"
    schedule_id: unspool-hourly-maintenance
  nightly-batch:
    schedule: "0 3 * * *"
    schedule_id: unspool-nightly-batch
```
Registered with QStash on startup. Stale `unspool-*` schedules are cleaned up before registration.

### `graph.yaml` — Graph Parameters
```yaml
retrieval:
  semantic_limit: 15
  graph_walk_hops: 1
  max_subgraph_nodes: 100
evolution:
  embedding_model: gemini-embedding-001
  dedup_threshold: 0.9
  edge_decay_factor: 0.99
  edge_decay_min: 0.01
ingest:
  model: gemini-2.5-flash
  max_nodes: 10
```

### `proactive.yaml` — Proactive Triggers
5 triggers evaluated in priority order. Only the first matching trigger fires per session. 6-hour cooldown between proactive messages.

| Trigger | Condition | Priority |
|---------|-----------|----------|
| `deadline_imminent` | OPEN items with deadlines in 24h | 1 |
| `long_absence` | No interaction for 7+ days | 2 |
| `something_slipped` | Soft deadlines passed during 3+ day absence | 3 |
| `momentum` | 3+ items completed in last 24h | 4 |
| `welcome_back` | Returns after 3+ days | 5 |

### `patterns.yaml` — Pattern Detection
```yaml
analyses:
  completion_stats:    # db_only — SQL aggregation
  behavioral_patterns: # llm_analysis — prompt + Gemini
  preference_inference: # llm_analysis
  memory_consolidation: # llm_analysis, run_on: process_conversation
```

### `scoring.yaml` — Urgency/Notifications
```yaml
notifications:
  quiet_hours_start: 1   # AM
  quiet_hours_end: 7     # AM
  deadline_window_hours: 24
```

## Prompt Templates

All in `backend/prompts/`. Jinja2 with YAML frontmatter, rendered via `SandboxedEnvironment`. User input in `user_message`, `message`, and `raw_text` variables is auto-escaped to prevent Jinja2 injection.

| Template | Used By | Variables |
|----------|---------|-----------|
| `agent_system.md` | Hot path system prompt | `profile`, `context`, `current_time` |
| `proactive_deadline.md` | Proactive engine | `items`, `profile` |
| `proactive_long_absence.md` | Proactive engine | `days_absent`, `profile` |
| `proactive_slipped.md` | Proactive engine | `items`, `days_absent`, `profile` |
| `proactive_momentum.md` | Proactive engine | `completion_count`, `profile` |
| `proactive_welcome_back.md` | Proactive engine | `days_absent`, `profile` |
| `detect_behavioral_patterns.md` | Pattern detection | `completion_data`, `message_activity`, `current_patterns`, `lookback_days` |
| `detect_preferences.md` | Pattern detection | `messages`, `current_profile`, `lookback_days` |
| `consolidate_memories.md` | Memory consolidation | `nodes` |
