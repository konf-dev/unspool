# Testing Guide

How to set up, test, and verify the Unspool V2 backend. These steps are designed to be reproducible after every code change or deployment.

## Prerequisites

- Python 3.12+ (tested on 3.14)
- PostgreSQL via Supabase (remote)
- `.env` file at repo root with all credentials (see [Configuration](configuration.md))

## Local Setup

```bash
cd backend/

# Create virtual environment
python3 -m venv .venv

# Install dependencies
.venv/bin/pip install -r requirements.txt

# Symlink .env from repo root (pydantic-settings reads from CWD)
ln -sf ../.env .env

# Verify settings load
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from src.core.settings import get_settings
s = get_settings()
print(f'env={s.ENVIRONMENT} db={s.DATABASE_URL[:50]}... llm={s.LLM_MODEL}')
"
```

## Database Setup

Apply migrations to a clean Supabase instance:

```bash
# Connection string (from .env, without the +asyncpg prefix)
export PGURL="postgresql://postgres.YOUR_PROJECT:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

# Drop everything (DESTRUCTIVE — only on dev/staging)
PGPASSWORD=... psql "$PGURL" -c "
DROP VIEW IF EXISTS vw_messages, vw_actionable, vw_timeline, vw_metrics CASCADE;
DROP TABLE IF EXISTS error_log, llm_usage, proactive_messages, scheduled_actions,
  push_subscriptions, subscriptions, graph_edges, graph_nodes, event_stream,
  user_profiles CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS public.on_auth_user_created() CASCADE;
"

# Apply all 6 migrations in order
for f in supabase/migrations/0000*.sql; do
  echo "Applying $f..."
  PGPASSWORD=... psql "$PGURL" -f "$f"
done

# Verify: should show 10 tables + 4 views
PGPASSWORD=... psql "$PGURL" -c "
SELECT 'TABLE' as type, tablename as name FROM pg_tables WHERE schemaname='public'
UNION ALL SELECT 'VIEW', viewname FROM pg_views WHERE schemaname='public'
ORDER BY type, name;
"
```

Expected output: 10 TABLEs (`error_log`, `event_stream`, `graph_edges`, `graph_nodes`, `llm_usage`, `proactive_messages`, `push_subscriptions`, `scheduled_actions`, `subscriptions`, `user_profiles`) + 4 VIEWs (`vw_actionable`, `vw_messages`, `vw_metrics`, `vw_timeline`).

## Start the Server

```bash
cd backend/
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
```

You should see:
```
info  app.starting  environment=development
info  db.pool_initialized
Uvicorn running on http://0.0.0.0:8000
```

## Smoke Test Script

Run these sequentially. Every command should produce the expected output.

```bash
BASE="http://localhost:8000"
AUTH="Authorization: Bearer eval:YOUR_EVAL_API_KEY"
ADMIN="X-Admin-Key: YOUR_ADMIN_API_KEY"
```

### 1. Health & Dependencies

```bash
# Basic health (DB connectivity)
curl -s $BASE/health
# Expected: {"status":"ok","version":"2.0.0","git_sha":"..."}

# Deep health (all 4 services)
curl -s -H "$ADMIN" $BASE/admin/health/deep
# Expected: status=ok for db, redis, qstash, langfuse
```

### 2. Authentication

```bash
# No token → 401
curl -s $BASE/api/messages
# {"detail":"Missing Bearer token"}

# Bad JWT → 401
curl -s -H "Authorization: Bearer garbage" $BASE/api/messages
# {"detail":"Invalid token"}

# Bad eval key → 401
curl -s -H "Authorization: Bearer eval:wrong" $BASE/api/messages
# {"detail":"Invalid eval key"}

# Valid eval token → 200
curl -s -H "$AUTH" "$BASE/api/messages?limit=1"
# {"messages":[],"has_more":false}

# Admin: no key → 403
curl -s $BASE/admin/health/deep
# {"detail":"Invalid admin key"}

# Jobs: no QStash sig → 403
curl -s -X POST $BASE/jobs/hourly-maintenance
# {"detail":"Missing Upstash-Signature header"}
```

### 3. Chat Pipeline (End-to-End)

```bash
# Send a message
curl -s -X POST $BASE/api/chat \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"message":"remember my cat is named Luna","session_id":"test-1","timezone":"UTC"}' \
  --max-time 30 | grep "^data:"
# Should see: tool_start, tool_end, token, done events

# Verify message persisted
curl -s -H "$AUTH" "$BASE/api/messages?limit=2"
# Should contain both user message and assistant response

# Verify LLM usage recorded
curl -s -H "$ADMIN" "$BASE/admin/jobs/recent?limit=3"
# Should show hot_path pipeline entries with token counts
```

### 4. Input Validation

```bash
# Empty message → 422
curl -s -X POST $BASE/api/chat \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"message":"","session_id":"t","timezone":"UTC"}'
# {"detail":[{"type":"string_too_short",...}]}

# Missing session_id → 422
curl -s -X POST $BASE/api/chat \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"message":"hello"}'
# {"detail":[{"type":"missing","loc":["body","session_id"],...}]}
```

### 5. Push Subscriptions

```bash
# Register a push subscription
curl -s -X POST $BASE/api/push/subscribe \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"endpoint":"https://fcm.example.com/test","keys":{"p256dh":"testkey","auth":"testauth"}}'
# {"status":"subscribed"}
```

### 6. Stripe (if configured)

```bash
# Create checkout (returns Stripe URL or 500 if not configured)
curl -s -X POST $BASE/api/subscribe -H "$AUTH"
# {"url":"https://checkout.stripe.com/..."} or {"detail":"Could not create checkout session"}

# Webhook without signature → 400
curl -s -X POST $BASE/api/webhooks/stripe
# {"detail":"Missing Stripe-Signature header"}
```

### 7. Email Webhook

```bash
# Without signature → 403
curl -s -X POST $BASE/webhooks/email/inbound
# {"detail":"Email webhook not configured"} or {"detail":"Missing X-Webhook-Signature header"}
```

### 8. ICS Feed

```bash
# Bad token → 404
curl -s $BASE/api/feed/nonexistent.ics
# {"detail":"Feed not found"}
```

### 9. Admin Endpoints

```bash
# User messages
curl -s -H "$ADMIN" "$BASE/admin/user/b8a2e17e-ff55-485f-ad6c-29055a607b33/messages?limit=5"

# User graph
curl -s -H "$ADMIN" "$BASE/admin/user/b8a2e17e-ff55-485f-ad6c-29055a607b33/graph?limit=5"

# User profile
curl -s -H "$ADMIN" "$BASE/admin/user/b8a2e17e-ff55-485f-ad6c-29055a607b33/profile"

# Trace lookup (use a trace_id from a previous chat)
curl -s -H "$ADMIN" "$BASE/admin/trace/YOUR_TRACE_ID"

# Error log
curl -s -H "$ADMIN" "$BASE/admin/errors?limit=5"

# Error summary (24h)
curl -s -H "$ADMIN" "$BASE/admin/errors/summary"
```

### 10. GDPR Account Deletion

```bash
# Create some data first
curl -s -X POST $BASE/api/chat \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"message":"test data","session_id":"gdpr-test","timezone":"UTC"}' \
  --max-time 30 | grep "^data:" | tail -1

# Register a push sub
curl -s -X POST $BASE/api/push/subscribe \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"endpoint":"https://test.example.com","keys":{"p256dh":"k","auth":"a"}}'

# Delete everything
curl -s -X DELETE $BASE/api/account -H "$AUTH"
# {"deleted":true,"rows_deleted":N,"details":{"events":...,"errors":...,"llm_usage":...}}

# Verify nothing remains
curl -s -H "$AUTH" "$BASE/api/messages?limit=1"
# {"messages":[],"has_more":false}

curl -s -H "$ADMIN" "$BASE/admin/user/b8a2e17e-ff55-485f-ad6c-29055a607b33/messages?limit=1"
# [] (empty)
```

### 11. Eval Cleanup (Admin)

```bash
# Create data, then clean up
curl -s -X DELETE -H "$ADMIN" "$BASE/admin/eval-cleanup"
# {"user_id":"b8a2e17e-ff55-485f-ad6c-29055a607b33","deleted":{"events":N,...}}
```

## What Can't Be Tested Locally

These require a production deployment where QStash can reach the public API URL:

| Feature | Why |
|---------|-----|
| **Cold path graph population** | QStash dispatches to `API_URL/jobs/process-message` — rejects localhost |
| **ICS feed with real data** | Needs graph nodes with HAS_DEADLINE edges (created by cold path) |
| **Proactive messages** | Needs user_profile with interaction history + graph data |
| **Scheduled action dispatch** | QStash `dispatch_at` needs public URL |
| **Cron schedule registration** | Only runs when `ENVIRONMENT != development` |

## QStash Connectivity Test

Verify QStash token and SDK work:

```bash
cd backend/
.venv/bin/python -c "
import asyncio, sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env')
async def test():
    from src.integrations.qstash import list_schedules, _get_client
    schedules = await list_schedules()
    print(f'Schedules: {len(schedules)}')
    for s in schedules:
        print(f'  {getattr(s, \"schedule_id\", \"?\")} -> {getattr(s, \"destination\", \"?\")}')
    client = _get_client()
    resp = await client.message.publish_json(url='https://httpbin.org/post', body={'test': True})
    print(f'Publish OK: {getattr(resp, \"message_id\", resp)}')
asyncio.run(test())
"
```

## Unit Tests

```bash
cd backend/
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/pytest tests/ -v
```

Test modules:
- `test_auth.py` — JWT, eval token, admin key verification
- `test_graph_operations.py` — Event append, node creation, PII scrubbing
- `test_tools.py` — query_graph/mutate_graph parameter validation
- `test_cold_path.py` — Idempotency keys, extraction schema parsing
- `test_chat.py` — Request validation, config loading, prompt rendering
- `test_proactive.py` — Condition evaluator registry, config validation
