# API Reference

Base URL: `https://api.unspool.life` (production) / `http://localhost:8000` (dev)

**22 endpoints** across 6 routers. All authenticated endpoints require `Authorization: Bearer <token>` unless noted.

---

## Public

### `GET /health`
No auth.

```json
// 200
{"status": "ok", "version": "2.0.0", "git_sha": "07d8933"}

// DB unreachable
{"status": "degraded", "db": "unreachable", "git_sha": "07d8933"}
```

### `GET /docs`
OpenAPI Swagger UI. **Disabled in production** (`ENVIRONMENT != development`).

---

## Chat — `/api`

### `POST /api/chat`
**Auth:** Supabase JWT or `eval:<EVAL_API_KEY>`
**Rate Limited:** Yes (tier from `gate.yaml`, checked via Redis)

Streams an AI response via Server-Sent Events.

**Request:**
```json
{
  "message": "I need to finish my thesis by Friday",   // required, 1-10000 chars
  "session_id": "sess-abc123",                          // required, 1-100 chars
  "timezone": "America/New_York"                        // optional, max 50 chars
}
```

**Response:** `Content-Type: text/event-stream`

```
data: {"type": "tool_start", "calls": ["query_graph"]}
data: {"type": "tool_end", "name": "query_graph"}
data: {"type": "token", "content": "Got it, I'll remember that."}
data: {"type": "done"}
```

**Headers:** `X-Trace-Id: <uuid>`, `Cache-Control: no-cache`, `Connection: keep-alive`

**Errors:**
| Code | Detail |
|------|--------|
| 401 | Missing/invalid JWT, bad eval key |
| 422 | Validation: empty message, missing session_id |
| 429 | Rate limit exceeded (message from gate.yaml) |

**Pipeline (in order):**
1. Auth → rate limit check
2. Sync timezone to profile (if provided)
3. Persist user message as `MessageReceived` event
4. Assemble context in parallel: profile, last 20 messages, graph semantic search, 72h deadlines
5. Stream LangGraph hot path (GPT model with query_graph + mutate_graph tools, max 5 iterations)
6. Strip `<thought>` blocks from output
7. Persist assistant response as `AgentReplied` event
8. Dispatch cold path extraction via QStash (5s delay)
9. On timeout (60s) or error: send graceful error message, still persist

---

### `GET /api/messages`
**Auth:** Supabase JWT or eval token

Paginated chat history projected from `vw_messages` view.

**Query Params:**
| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `limit` | int | 50 | 1-100 |
| `before` | string | null | Event UUID for cursor pagination |

**Response:**
```json
{
  "messages": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "role": "user",
      "content": "finish thesis by Friday",
      "metadata": {"trace_id": "uuid", "session_id": "string"},
      "created_at": "2026-03-23T10:00:00+00:00"
    },
    {
      "id": "uuid",
      "user_id": "uuid",
      "role": "assistant",
      "content": "Got it.",
      "metadata": {"trace_id": "uuid", "session_id": "string"},
      "created_at": "2026-03-23T10:00:05+00:00"
    }
  ],
  "has_more": true
}
```

**On initial load** (no `before` param):
1. Evaluates proactive triggers from `proactive.yaml` (6h cooldown)
2. Delivers queued `proactive_messages` (marks as delivered)
3. Proactive messages prepended to results

---

## Subscriptions — `/api`

### `POST /api/subscribe`
**Auth:** Supabase JWT

Creates a Stripe checkout session for the paid tier ($8/month).

**Response:**
```json
{"url": "https://checkout.stripe.com/c/pay/..."}
```
Returns `500` with `"Could not create checkout session"` if `STRIPE_SECRET_KEY` is not configured.

---

### `POST /api/push/subscribe`
**Auth:** Supabase JWT

Registers a Web Push subscription endpoint.

**Request:**
```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "keys": {
    "p256dh": "BNcRd...",
    "auth": "tBHI..."
  }
}
```

**Response:**
```json
{"status": "subscribed"}
```
Idempotent — duplicate (user_id, endpoint) pairs are ignored.

---

### `POST /api/webhooks/stripe`
**Auth:** `Stripe-Signature` header (verified via `STRIPE_WEBHOOK_SECRET`)

Handles Stripe webhook events:
| Event | Action |
|-------|--------|
| `checkout.session.completed` | Create subscription, invalidate Redis tier cache |
| `customer.subscription.deleted` | Set tier=free, status=cancelled |
| `invoice.payment_failed` | Set status=past_due |

Returns `400` if signature missing or invalid.

---

## Account — `/api`

### `DELETE /api/account`
**Auth:** Supabase JWT

**GDPR-compliant cascading delete** of ALL user data across all 10 tables:

```json
{
  "deleted": true,
  "rows_deleted": 42,
  "details": {
    "events": 30,
    "edges": 5,
    "nodes": 3,
    "proactive": 0,
    "actions": 0,
    "push_subs": 1,
    "subscriptions": 1,
    "profiles": 1,
    "errors": 1,
    "llm_usage": 4
  }
}
```

Deletion order (FK-safe): events → edges → nodes → proactive → actions → push_subs → subscriptions → profiles → errors → llm_usage.

---

## ICS Feed — `/api`

### `GET /api/feed/{token}.ics`
**Auth:** Token-in-URL (no auth header). The `token` is the user's `feed_token` from `user_profiles`.

Returns an ICS calendar with deadline events from `vw_timeline` (last 30 days + future).

**Response:** `Content-Type: text/calendar`

Returns `404 "Feed not found"` for invalid tokens.

---

## Webhooks

### `POST /webhooks/email/inbound`
**Auth:** HMAC-SHA256 signature in `X-Webhook-Signature` header, verified against `EMAIL_WEBHOOK_SECRET`.

Receives forwarded emails (SendGrid Inbound Parse / Postmark format). Maps `to` address local part to `user_profiles.email_alias`, dispatches message body to cold path via QStash.

**Expected form fields:** `from`, `to`, `text`

**Errors:**
| Code | Detail |
|------|--------|
| 403 | Email webhook not configured / missing signature / invalid signature |
| 404 | Unknown email alias |

---

## Background Jobs — `/jobs`

All endpoints require QStash signature verification (`Upstash-Signature` header). Returns `403` without valid signature.

### `POST /jobs/synthesis`
Run nightly synthesis for a single user.
```json
// Request
{"user_id": "uuid"}
// Response
{"status": "success", "result": {"archived": 2, "merged": 1, "decayed": 50, "views_refreshed": true}}
```

### `POST /jobs/hourly-maintenance`
Runs sequentially: `check_deadlines`, `execute_actions`, `expire_items`. Each sub-job catches its own errors.
```json
{
  "check_deadlines": {"notified": 1, "skipped": 3},
  "execute_actions": {"executed": 2, "failed": 0},
  "expire_items": {"expired_hard": 0}
}
```

### `POST /jobs/nightly-batch`
Runs: `reset_notifications`, `detect_patterns`, then nightly synthesis for all active users (last 30 days).
```json
{
  "reset_notifications": {"reset": 5},
  "detect_patterns": {"updated": 3, "llm_calls": 2},
  "synthesis": {"users_processed": 3}
}
```

### `POST /jobs/process-message`
Cold path extraction for a single message (dispatched by chat endpoint via QStash).
```json
// Request
{"user_id": "uuid", "trace_id": "uuid", "message": "I need to finish my thesis"}
// Response
{"status": "processed"}
```

### `POST /jobs/execute-action`
Execute specific scheduled actions by ID (dispatched by `qstash.dispatch_at`).
```json
// Request
{"action_ids": ["uuid1", "uuid2"]}
// Response
{"executed": 1, "failed": 0, "skipped": 1}
```

---

## Admin — `/admin`

All endpoints require `X-Admin-Key` header matching `ADMIN_API_KEY` env var. Returns `403` without valid key.

### `GET /admin/trace/{trace_id}`
```json
{
  "trace_id": "uuid",
  "events": [{"id": "uuid", "user_id": "uuid", "event_type": "MessageReceived", "payload": {...}, "created_at": "..."}],
  "llm_usage": [{"id": "uuid", "pipeline": "hot_path", "model": "gpt-4o-mini", "input_tokens": 1514, "output_tokens": 41, "latency_ms": 1481, "created_at": "..."}]
}
```

### `GET /admin/user/{user_id}/messages?limit=50`
Returns user's chat history from `vw_messages`. Max limit 200.

### `GET /admin/user/{user_id}/graph?limit=100`
```json
{
  "nodes": [{"id": "uuid", "content": "Buy milk", "node_type": "action", "created_at": "...", "updated_at": "..."}],
  "edges": [{"id": "uuid", "source_node_id": "uuid", "target_node_id": "uuid", "edge_type": "IS_STATUS", "weight": 1.0, "metadata": {}, "created_at": "..."}]
}
```
Max limit 500.

### `GET /admin/user/{user_id}/profile`
Full user profile dict or `{"error": "Profile not found"}`.

### `GET /admin/jobs/recent?limit=20`
Recent LLM usage records (pipeline, model, tokens, latency). Max limit 100.

### `GET /admin/errors?limit=20&source=cold_path.extraction_failed`
Recent error log entries with full stacktraces. Optional `source` filter. Max limit 100.

### `GET /admin/errors/summary`
Aggregated error counts by (source, error_type) in last 24 hours.
```json
[{"source": "qstash.dispatch_failed", "error_type": "QStashError", "count": 3, "last_seen": "2026-03-23T21:13:59Z"}]
```

### `DELETE /admin/eval-cleanup`
Deletes all data for the eval user (`b8a2e17e-ff55-485f-ad6c-29055a607b33`). Used before eval runs.
```json
{"user_id": "b8a2e17e-ff55-485f-ad6c-29055a607b33", "deleted": {"events": 6, "edges": 0, ...}}
```

### `GET /admin/health/deep`
Parallel health check of all external dependencies.
```json
{
  "status": "ok",
  "git_sha": "07d8933",
  "environment": "development",
  "total_ms": 273,
  "services": {
    "db": {"status": "ok", "latency_ms": 264},
    "redis": {"status": "ok", "latency_ms": 187},
    "qstash": {"status": "ok", "latency_ms": 124},
    "langfuse": {"status": "ok", "latency_ms": 244}
  }
}
```
Returns `"status": "degraded"` if any service is in error state.
