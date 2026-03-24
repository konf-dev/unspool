# Observability — Debugging & Monitoring

How to see what's happening in production.

---

## Three tools, one picture

| Tool | What it shows | Access |
|------|--------------|--------|
| **Langfuse** | Trace waterfall per request — nested spans for LLM calls, tool executions, embeddings, latency, tokens, cost | [cloud.langfuse.com](https://cloud.langfuse.com) |
| **Admin API** | Same data via CLI — traces, user conversations, graph, errors | `curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/...` |
| **Railway logs** | Raw structured JSON logs, filter by trace_id/user_id | `railway logs` or Railway dashboard |

Supporting tools (no setup needed):
- **Supabase Dashboard** — SQL editor, all tables, user auth
- **QStash Console** — Cron schedules, delivery logs, retries, failures
- **Upstash Redis** — Cache inspection

---

## Langfuse

### What you see per request

Every chat request creates ONE trace with nested spans:

```
trace: "chat" (user_id=865776be, session_id=abc, tags=["chat"])
├─ span: "agent.assemble_context" (900ms)
│  └─ span: "embedding" (semantic search, task_type=RETRIEVAL_QUERY)
├─ chain: "LangGraph" (via CallbackHandler)
│  ├─ agent: iteration 0
│  │  └─ generation: gemini-2.5-flash (thinking + tool call)
│  ├─ tool: query_graph
│  │  └─ span: "embedding" (task_type=RETRIEVAL_QUERY)
│  └─ agent: iteration 1
│     └─ generation: gemini-2.5-flash (final response)
└─ Total: ~3-5s | user_id, session_id, tags visible

Cold path (separate trace, linked via metadata):
trace: "job.process_message" (user_id=865776be, tags=["cold_path","job"])
├─ span: "cold_path.process"
│  ├─ span: "cold_path.extraction"
│  │  └─ generation: gemini-2.5-flash (structured output, thinking_budget=8192)
│  ├─ span: "embedding" (dedup, task_type=SEMANTIC_SIMILARITY)
│  └─ span: "embedding.batch" (new nodes, task_type=RETRIEVAL_DOCUMENT)
└─ metadata: {parent_chat_trace_id: "..."}
```

### How tracing works

The tracing uses langfuse v4's `@observe` decorator with OpenTelemetry context propagation:

1. `@observe(name="chat")` on the streaming function creates the root trace
2. `propagate_trace_attributes()` sets user_id, session_id, tags on the trace
3. LangChain `CallbackHandler` inherits the OTEL context — traces all LangGraph agent iterations + LLM calls
4. `@observe` on cold path, embedding, and proactive functions creates child spans for direct Gemini SDK calls
5. LangGraph node functions (`call_model`, `call_tools`) are **not** decorated with `@observe` — the CallbackHandler handles that. Adding `@observe` to LangGraph nodes causes OTEL context detach errors.

All instrumentation no-ops when Langfuse is not configured (zero overhead).

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
| `_stream_response` | `@observe(name="chat")` | `src/api/chat.py` |
| `assemble_context` | `@observe(name="agent.assemble_context")` | `src/agents/hot_path/context.py` |
| `call_model` | `@observe(name="hot_path.call_model")` | `src/agents/hot_path/graph.py` |
| `call_tools` | `@observe(name="hot_path.call_tools")` | `src/agents/hot_path/graph.py` |
| `run_extraction` | `@observe(name="cold_path.extraction")` | `src/agents/cold_path/extractor.py` |
| `process_brain_dump` | `@observe(name="cold_path.process")` | `src/agents/cold_path/extractor.py` |
| `get_embedding` | `@observe(name="embedding")` | `src/integrations/openai.py` |
| `check_proactive` | `@observe(name="proactive.check")` | `src/proactive/engine.py` |
| `process_message` | `@observe(name="job.process_message")` | `src/jobs/router.py` |
| `nightly_batch` | `@observe(name="job.nightly_batch")` | `src/jobs/router.py` |
| `hourly_maintenance` | `@observe(name="job.hourly_maintenance")` | `src/jobs/router.py` |
| `synthesis` | `@observe(name="job.synthesis")` | `src/jobs/router.py` |

### CLI access to Langfuse

```bash
# Recent traces
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?limit=10" | jq

# Traces for a specific user
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?userId=865776be" | jq

# Inspect traces via helper script
python eval/inspect_traces.py chat      # Chat traces
python eval/inspect_traces.py jobs      # Job traces
python eval/inspect_traces.py cold_path # Cold path traces
python eval/inspect_traces.py summary   # All trace types summary
```

---

## Admin API

Protected by `ADMIN_API_KEY` env var, sent via `X-Admin-Key` header.

### Endpoints

```bash
KEY=$ADMIN_API_KEY

# Full trace for a request (messages + LLM usage breakdown)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/trace/{trace_id} | jq

# User's recent messages
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/messages | jq

# User's knowledge graph (nodes + edges)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/graph | jq

# User's profile
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/user/{user_id}/profile | jq

# Recent LLM usage
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/jobs/recent | jq

# Recent errors
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/errors | jq

# Error summary
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/errors/summary | jq

# Deep health check (all services)
curl -H "X-Admin-Key: $KEY" https://api.unspool.life/admin/health/deep | jq
```

### Getting the trace_id

Every chat response includes the trace_id in the `X-Trace-Id` response header. It's also stored in `messages.metadata.trace_id` for both user and assistant messages.

---

## Eval Framework

### Promptfoo (regression testing)

161 test cases across 8 categories. Tests run against the live API via SSE.

```bash
cd eval
npx promptfoo eval            # Run all tests
npx promptfoo view            # View results in browser
```

Config: `eval/promptfooconfig.yaml`. Test cases: `eval/cases/*.yaml`.

### Langfuse LLM-as-Judge (production scoring)

Fetches recent traces and scores them on 6 dimensions:

| Dimension | Applies to | What it checks |
|-----------|-----------|----------------|
| relevance | Chat | Did the response address the user's actual intent? |
| conciseness | Chat | Free of filler, unsolicited advice, cheerleading? |
| tone_match | Chat | Matches user's energy level? |
| safety | Chat | No PII leakage, jailbreak compliance, system prompt? |
| extraction_quality | Cold path | Correctly identified entities and relationships? |
| edge_completeness | Cold path | Every action has IS_STATUS, every deadline has HAS_DEADLINE? |

```bash
python eval/langfuse_eval.py              # Score recent chat traces
python eval/langfuse_eval.py --cold-path  # Score cold path traces
python eval/langfuse_eval.py --dry-run    # Print without posting
```

### Smoke Test (deploy verification)

Automated 36-test suite covering all API endpoints:

```bash
BASE_URL=https://api.unspool.life python eval/smoke_test.py
```

Tests: infrastructure, auth (7), validation (3), chat pipeline (5), cold path (2), graph context (2), admin (7), webhooks (4), feeds (1), GDPR deletion (3).

### Red Team

```bash
cd eval
npx promptfoo redteam run     # 50 attack scenarios
```

Plugins: prompt-extraction, PII, hijacking, excessive-agency, RBAC, cross-user-data, tool-abuse, system-prompt-extraction.

---

## Debugging workflows

### "User says something went wrong"

1. Get their user_id from Supabase Auth dashboard
2. Pull recent messages:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/user/{user_id}/messages | jq
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
3. Check if context assembly returned relevant graph nodes

### "Background job seems broken"

1. Check QStash console for delivery failures
2. Check Railway logs: `railway logs --filter "job.start"`
3. Look at Langfuse for job traces (`python eval/inspect_traces.py jobs`)

### "Cold path didn't extract correctly"

1. Find the `job.process_message` trace in Langfuse
2. Look at `cold_path.extraction` span — see the LLM's structured output
3. Check the `embedding` spans to see dedup matches
4. Use admin API to inspect the user's graph:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/user/{user_id}/graph | jq
   ```

### "Costs seem high"

1. Query LLM usage via admin API:
   ```bash
   curl -H "X-Admin-Key: $KEY" .../admin/jobs/recent | jq
   ```
2. Or use Langfuse dashboard → Analytics → Cost by model/trace
