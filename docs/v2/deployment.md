# Deployment Guide

## Railway

The backend deploys to Railway via Nixpacks. Config in `backend/railway.json`:

```json
{
  "build": {
    "builder": "NIXPACKS",
    "watchPatterns": ["src/**", "config/**", "prompts/**", "requirements.txt"]
  },
  "deploy": {
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3,
    "startCommand": "uvicorn src.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

### Required Environment Variables on Railway

Copy these from your `.env` to Railway's environment variable settings. **All are required for production.**

| Variable | Notes |
|----------|-------|
| `ENVIRONMENT` | Set to `production` |
| `DATABASE_URL` | Must include `+asyncpg` driver prefix |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Service role key (not anon key) |
| `GOOGLE_API_KEY` | Google AI Studio key (from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) |
| `CHAT_PROVIDER` | `gemini` |
| `CHAT_MODEL` | `gemini-2.5-flash` |
| `EXTRACTION_PROVIDER` | `gemini` |
| `EXTRACTION_MODEL` | `gemini-2.5-flash` |
| `BACKGROUND_PROVIDER` | `gemini` |
| `BACKGROUND_MODEL` | `gemini-2.5-flash` |
| `EMBEDDING_PROVIDER` | `gemini` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `QSTASH_TOKEN` | From Upstash Console → QStash |
| `QSTASH_URL` | e.g. `https://qstash-eu-central-1.upstash.io` (if EU region) |
| `QSTASH_CURRENT_SIGNING_KEY` | For webhook verification |
| `QSTASH_NEXT_SIGNING_KEY` | For key rotation |
| `UPSTASH_REDIS_REST_URL` | From Upstash Console → Redis |
| `UPSTASH_REDIS_REST_TOKEN` | |
| `ADMIN_API_KEY` | Strong random string for `/admin/*` endpoints |
| `EVAL_API_KEY` | For eval framework auth |
| `FRONTEND_URL` | e.g. `https://unspool.life` (CORS origin) |
| `API_URL` | e.g. `https://api.unspool.life` (QStash URL construction) |
| `VAPID_PRIVATE_KEY` | For Web Push (generate with `pywebpush`) |
| `VAPID_PUBLIC_KEY` | |

**Optional:**
| Variable | Notes |
|----------|-------|
| `STRIPE_SECRET_KEY` | Enable billing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification |
| `EMAIL_WEBHOOK_SECRET` | HMAC secret for inbound email |
| `LANGFUSE_HOST` | e.g. `https://cloud.langfuse.com` |
| `LANGFUSE_PUBLIC_KEY` | |
| `LANGFUSE_SECRET_KEY` | |
| `CORS_EXTRA_ORIGINS` | Comma-separated additional origins |

### Deploy Steps

1. Push code to `main` branch
2. Railway auto-builds from `backend/` directory
3. Health check at `/health` confirms DB connectivity
4. On first successful startup:
   - DB pool initialized
   - Cron schedules registered with QStash (stale ones cleaned up)

### Production Behaviors

When `ENVIRONMENT=production`:
- OpenAPI docs (`/docs`, `/redoc`) are disabled
- Log level is INFO (not DEBUG)
- Required env vars are validated on startup — missing ones crash the process
- QStash cron schedules are registered automatically
- Stale `unspool-*` schedules are cleaned up before registration

## Supabase

### Migrations

Migrations live in `backend/supabase/migrations/`. Apply in order:

| File | Creates |
|------|---------|
| `00001_v2_core_schema.sql` | `event_stream`, `graph_nodes`, `graph_edges` + RLS + pgvector |
| `00002_user_profiles.sql` | `user_profiles` + auto-create trigger on auth signup |
| `00003_subscriptions_and_push.sql` | `subscriptions`, `push_subscriptions` + RLS |
| `00004_proactive_and_scheduled.sql` | `proactive_messages`, `scheduled_actions` + RLS |
| `00005_operational.sql` | `error_log`, `llm_usage` (no RLS — admin only) |
| `00006_graph_views.sql` | `vw_messages`, `vw_actionable`, `vw_timeline`, `vw_metrics` |
| `00007_gemini_embeddings.sql` | Wipe embeddings, change `vector(1536)` → `vector(768)`, recreate HNSW index |
| `00008_fix_actionable_dedup.sql` | Fix duplicate items in `vw_actionable` view |
| `00009_view_and_index_optimizations.sql` | Composite indexes, optimized view queries |
| `00010_graph_node_unique_constraint.sql` | Unique constraint on `(user_id, content, node_type)` |
| `00011_migration_tracking.sql` | `schema_migrations` table + backfill of all existing migrations |

To apply, use the migration runner (see [Migration Protocol](#migration-protocol)):
```bash
./scripts/migrate.sh
```

### Row Level Security

All user-facing tables have RLS enabled with `auth.uid() = user_id` policies. The backend connects with the service role key which bypasses RLS. If you ever connect with the anon key, RLS is enforced.

## QStash

### Cron Schedules

Two cron jobs, registered automatically on production startup from `config/jobs.yaml`:

| Schedule ID | Cron | Endpoint |
|-------------|------|----------|
| `unspool-hourly-maintenance` | `0 * * * *` | `POST {API_URL}/jobs/hourly-maintenance` |
| `unspool-nightly-batch` | `0 3 * * *` | `POST {API_URL}/jobs/nightly-batch` |

### Manual Schedule Management

```bash
# List current schedules
curl -s -H "Authorization: Bearer $QSTASH_TOKEN" https://qstash.upstash.io/v2/schedules | python3 -m json.tool

# Delete a stale schedule
curl -s -X DELETE -H "Authorization: Bearer $QSTASH_TOKEN" https://qstash.upstash.io/v2/schedules/SCHEDULE_ID
```

### EU Region

If your QStash instance is in EU, set `QSTASH_URL=https://qstash-eu-central-1.upstash.io` in your env. The SDK will use this as base URL instead of the default US endpoint.

## Migration Protocol

Migrations are tracked in a `schema_migrations` table and applied via `scripts/migrate.sh`. Never apply migrations with a raw `psql` loop — always use the runner.

### Deploy Order

```bash
# 1. Preview what will change
./scripts/migrate.sh --dry-run

# 2. Backup + apply (automatic)
./scripts/migrate.sh

# 3. Deploy backend + frontend
git push origin main

# 4. Verify everything
./scripts/diagnose.sh
```

### Script Options

| Flag | Effect |
|------|--------|
| `--dry-run` | Show pending migrations without applying |
| `--status` | Show applied/pending/modified counts |
| `--no-backup` | Skip `pg_dump` backup (local dev / re-runs) |
| `--force` | Apply destructive migrations without confirmation |

### Safety Features

- **Automatic backup**: `pg_dump` before every migration run (stored in `backups/`, gitignored)
- **Checksum tracking**: SHA-256 of each `.sql` file recorded; warns if a file changes after being applied
- **Destructive guard**: `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM` require `--force` or interactive confirmation
- **Idempotent bootstrap**: The runner creates `schema_migrations` if it doesn't exist, so it works on a fresh DB

### Writing New Migrations

1. Create `backend/supabase/migrations/00NNN_description.sql`
2. Use `IF NOT EXISTS` / `IF EXISTS` where possible for idempotency
3. Run `./scripts/migrate.sh --dry-run` to verify it's detected
4. Run `./scripts/migrate.sh` to apply

### Backups

On Supabase Free tier, daily backups exist but **cannot be restored**. The `migrate.sh` script runs `pg_dump` automatically before applying migrations. Each backup gets a companion `.manifest.txt` with the git commit, applied migrations, tables, and views — so you know exactly what state the backup represents.

Backups are stored in `backups/` (gitignored, keeps last 5). To restore:

```bash
source .env
PGURL="${DATABASE_URL//+asyncpg/}"
# Check the manifest first to see what's in the backup
cat backups/backup_XXXX.manifest.txt
# Restore
gunzip -c backups/backup_XXXX.sql.gz | psql "$PGURL"
```

## Post-Deploy Verification

After deploying to Railway, run these against the production URL:

```bash
BASE="https://api.unspool.life"

# 1. Health
curl -s $BASE/health

# 2. Deep health
curl -s -H "X-Admin-Key: YOUR_KEY" $BASE/admin/health/deep

# 3. Auth works
curl -s $BASE/api/messages  # should be 401

# 4. Eval auth works
curl -s -H "Authorization: Bearer eval:YOUR_EVAL_KEY" "$BASE/api/messages?limit=1"

# 5. Chat pipeline
curl -s -X POST $BASE/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eval:YOUR_EVAL_KEY" \
  -d '{"message":"hello","session_id":"deploy-test","timezone":"UTC"}' \
  --max-time 30 | grep "^data:" | tail -2

# 6. Verify cold path dispatched (check QStash dashboard or admin errors)
curl -s -H "X-Admin-Key: YOUR_KEY" "$BASE/admin/errors?limit=3"
```
