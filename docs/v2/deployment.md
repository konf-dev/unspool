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
| `LLM_API_KEY` | OpenAI API key |
| `LLM_MODEL` | e.g. `gpt-4o-mini` or `gpt-4.1` |
| `LLM_MODEL_FAST` | e.g. `gpt-4o-mini` |
| `EMBEDDING_API_KEY` | Can be same as LLM_API_KEY |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |
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

To apply:
```bash
for f in backend/supabase/migrations/0000*.sql; do
  PGPASSWORD=... psql "$PGURL" -f "$f"
done
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
