# Observability — Debugging & Monitoring

How to see what's happening in production.

---

## Three tools, one picture

| Tool | What it shows | Access |
|------|--------------|--------|
| **Langfuse** | Trace waterfall per request — prompts sent, LLM responses, tool I/O, latency, tokens, cost | [cloud.langfuse.com](https://cloud.langfuse.com) |
| **Admin API** | Same data via CLI — traces, user conversations, items, errors | `curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/...` |
| **Railway logs** | Raw structured JSON logs, filter by trace_id/user_id | `railway logs` or Railway dashboard |

Supporting tools (no setup needed):
- **Supabase Dashboard** — SQL editor, all tables, user auth
- **QStash Console** — Cron schedules, delivery logs, retries, failures
- **Upstash Redis** — Cache inspection

---

## Langfuse

### What you see per request

```
Trace: da50f775 | user: 865776be | "hey, what are my reminders"
├─ classify_intent (450ms)
│  ├─ Prompt: "Classify the user's message..."
│  ├─ Response: {"intent": "query_search", "confidence": 0.9}
│  └─ Tokens: 240 in / 15 out
├─ assemble_context (900ms)
│  └─ Fields loaded: profile, recent_messages
├─ pipeline: query_search
│  ├─ analyze [generation] (1200ms)
│  │  ├─ Prompt: "Determine what data to fetch..."
│  │  ├─ Response: {"search_type": "status", ...}
│  │  └─ Tokens: 683 in / 57 out
│  ├─ smart_fetch [span] (450ms)
│  │  ├─ Input: {sources: ["items"], status: "open"}
│  │  └─ Output: 3 items found
│  └─ respond [generation] (1500ms)
│     ├─ Prompt: "Answer using fetched data..."
│     ├─ Response: "You've got a reminder to call Dad and..."
│     └─ Tokens: 500 in / 40 out
└─ Total: 4.5s | 1423 in / 112 out
```

### Setup

1. Sign up at [cloud.langfuse.com](https://cloud.langfuse.com), create project "unspool"
2. Get API keys from Settings → API Keys
3. Set in Railway env vars:
   ```
   LANGFUSE_HOST=https://cloud.langfuse.com
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

Cloud free tier gives 50k observations/month — plenty for MVP.

### Instrumented functions

| Function | Decorator | File |
|----------|-----------|------|
| `_stream_response` | `@observe("chat.stream_response")` | `src/api/chat.py` |
| `classify_intent` | `@observe("classify_intent")` | `src/orchestrator/intent.py` |
| `assemble_context` | `@observe("assemble_context")` | `src/orchestrator/context.py` |
| `execute_pipeline` | `@observe("execute_pipeline")` | `src/orchestrator/engine.py` |
| `_execute_llm_step` | `@observe_generation("llm_step")` | `src/orchestrator/engine.py` |
| `_execute_tool_step` | `@observe("tool_step")` | `src/orchestrator/engine.py` |
| `smart_fetch` | `@observe("smart_fetch")` | `src/tools/query_tools.py` |
| `run_process_conversation` | `@observe("job.process_conversation")` | `src/jobs/process_conversation.py` |
| `run_check_deadlines` | `@observe("job.check_deadlines")` | `src/jobs/check_deadlines.py` |
| `run_decay_urgency` | `@observe("job.decay_urgency")` | `src/jobs/decay_urgency.py` |
| `run_detect_patterns` | `@observe("job.detect_patterns")` | `src/jobs/detect_patterns.py` |
| `run_sync_calendar` | `@observe("job.sync_calendar")` | `src/jobs/sync_calendar.py` |
| `run_reset_notifications` | `@observe("job.reset_notifications")` | `src/jobs/reset_notifications.py` |

### CLI access to Langfuse

```bash
# Recent traces
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?limit=10" | jq

# Traces for a specific user
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?userId=865776be" | jq
```

### No-op when unconfigured

If `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, or `LANGFUSE_SECRET_KEY` are empty, all `@observe` decorators become no-ops. No performance overhead, no errors. The wrapper lives in `src/telemetry/langfuse_integration.py`.

---

## Admin API

Protected by `ADMIN_API_KEY` env var. Set it in Railway:

```bash
# Generate a key
openssl rand -hex 32
```

### Endpoints

```bash
# Full trace for a request (messages + LLM usage breakdown)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/trace/{trace_id} | jq

# User's recent conversation
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/messages?limit=50 | jq

# User's open items
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/items?status=open | jq

# User's full profile (including patterns)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/profile | jq

# Recent LLM usage (what the system has been doing)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/jobs/recent?limit=20 | jq

# Recent errors (pipeline crashes, timeouts)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/errors?limit=20 | jq
```

### Getting the trace_id

Every chat response includes the trace_id in the `X-Trace-Id` response header. It's also stored in `messages.metadata.trace_id` for both user and assistant messages.

---

## Debugging workflows

### "User says something went wrong"

1. Get their user_id from Supabase Auth dashboard
2. Pull recent conversation:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/user/{user_id}/messages?limit=10 | jq
   ```
3. Find the message with `metadata.error=true`, grab its `trace_id`
4. Inspect the trace:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/trace/{trace_id} | jq
   ```
5. Open the same trace in Langfuse dashboard for the visual waterfall

### "LLM is giving weird responses"

1. Find the trace in Langfuse
2. Look at the generation spans — you'll see the exact prompt sent and the exact response received
3. Check if the prompt template rendered correctly (look for empty variables, missing context)

### "Background job seems broken"

1. Check QStash console for delivery failures
2. Check Railway logs: `railway logs --filter "job.start"`
3. Look at Langfuse for job traces (all job runners are instrumented)

### "Costs seem high"

1. Query LLM usage via admin API:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/jobs/recent?limit=100 | jq '[.[] | {pipeline, model, input_tokens, output_tokens}] | group_by(.pipeline) | map({pipeline: .[0].pipeline, total_in: (map(.input_tokens) | add), total_out: (map(.output_tokens) | add)})'
   ```
2. Or use Langfuse dashboard → Analytics → Cost by model/trace

---

## Testing

### Test suite

```bash
cd backend
pytest -v --timeout=30     # Full suite (218 tests)
```

Test categories:

| File | What it tests |
|------|--------------|
| `test_system_prompt.py` | All 26 prompts render with empty + realistic data |
| `test_json_extraction.py` | `_extract_json()` with all LLM output patterns |
| `test_pipeline_execution.py` | brain_dump + query_search flows with MockLLMProvider |
| `test_chat_endpoint.py` | `/api/chat` SSE streaming, auth, error/timeout handling |
| `test_smart_fetch.py` | Query tool with various query_spec shapes |
| `test_intent.py` | Intent classification edge cases |
| Other test files | Config loading, Redis, auth, tools, scoring, patterns |

### CI

GitHub Actions runs on every push/PR to `main`:

1. `ruff check .` — linting (unused imports, undefined names, etc.)
2. `ruff format --check .` — formatting consistency
3. `pytest -x --timeout=30` — full test suite

Fix formatting issues locally with `ruff format .`.
