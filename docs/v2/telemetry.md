# Telemetry & Observability

## Structured Logging (`src/telemetry/logger.py`)

Uses `structlog` with stdlib integration.

- **Development:** `ConsoleRenderer` (colored, human-readable), DEBUG level
- **Production:** `JSONRenderer` (machine-parseable), INFO level
- Uvicorn access logs suppressed (WARNING level)

Usage:
```python
from src.telemetry.logger import get_logger
_log = get_logger("module.name")
_log.info("event.name", key="value", count=42)
```

## Trace Middleware (`src/telemetry/middleware.py`)

ASGI middleware on every HTTP request:

1. Generates UUID `trace_id`
2. Stores in `scope["state"]["trace_id"]` (accessible to handlers)
3. Binds to structlog contextvars (auto-included in all log messages)
4. Adds `x-trace-id` response header
5. Logs `request.start` and `request.end` with method, path, status_code, latency_ms
6. Includes `git_sha` from `GIT_SHA` or `RAILWAY_GIT_COMMIT_SHA` env var

## Error Reporting (`src/telemetry/error_reporting.py`)

`report_error(source, error, trace_id?, user_id?, **extra)` writes to 3 sinks:

1. **structlog** — Full traceback (always, goes to Railway logs)
2. **Langfuse** — Marks current observation as ERROR via `update_current_span(level="ERROR")` (if configured)
3. **DB error_log** — Fire-and-forget async persist (won't crash caller if DB fails)

The DB persist resolves `trace_id` from structlog contextvars if not provided.

## Langfuse Integration (`src/telemetry/langfuse_integration.py`)

Uses langfuse v4's `@observe` decorator with OpenTelemetry context propagation. Provider-agnostic — works with Gemini, OpenAI, or any LLM backend. The LangChain `CallbackHandler` auto-instruments all LangGraph agent iterations.

### Known Issue: OTEL Context Detach Warning

When using Langfuse's `CallbackHandler` with LangGraph's `astream()`, OpenTelemetry logs "Failed to detach context" warnings. This is a [confirmed upstream bug](https://github.com/langfuse/langfuse/issues/8780) in langfuse v4 — OTEL context tokens created in LangGraph's `TaskGroup` can't be cleanly detached across async task boundaries. **Traces still reach Langfuse correctly.** The OTEL logger is suppressed to `CRITICAL` level to eliminate the noise.

### Exports

| Function | Purpose |
|----------|---------|
| `observe` | Decorator — wraps `langfuse.observe` (creates OTEL spans). No-ops if unconfigured. |
| `propagate_trace_attributes(user_id, session_id, tags, metadata)` | Context manager to set trace-level attributes on all child spans. |
| `update_current_observation(**kwargs)` | Update the current active span (level, output, metadata, etc.) |
| `get_langchain_handler_from_context()` | Create a LangChain `CallbackHandler` that inherits current `@observe` trace context. |
| `flush_langfuse()` | Flush pending events. Called at end of SSE stream. |
| `is_langfuse_available()` | Check if Langfuse is configured and importable. |

### How it works

1. `@observe(name="chat")` on the SSE stream function creates an OTEL span → becomes the Langfuse trace
2. `propagate_trace_attributes(user_id=..., session_id=..., tags=...)` sets trace metadata
3. `CallbackHandler()` created inside an observe scope inherits the OTEL context — all LangGraph spans nest under the trace
4. Direct Gemini SDK calls (cold path, proactive, patterns) are traced via `@observe` decorators on those functions
5. Embedding calls are traced via `@observe(name="embedding")` on `get_embedding()` and `get_embeddings_batch()`

### Instrumented functions

| Function | Decorator | File |
|----------|-----------|------|
| `_stream_response` | `@observe(name="chat")` | `src/api/chat.py` |
| `assemble_context` | `@observe(name="agent.assemble_context")` | `src/agents/hot_path/context.py` |
| `run_extraction` | `@observe(name="cold_path.extraction")` | `src/agents/cold_path/extractor.py` |
| `process_brain_dump` | `@observe(name="cold_path.process")` | `src/agents/cold_path/extractor.py` |
| `get_embedding` | `@observe(name="embedding")` | `src/integrations/gemini.py` |
| `get_embeddings_batch` | `@observe(name="embedding.batch")` | `src/integrations/gemini.py` |
| `check_proactive` | `@observe(name="proactive.check")` | `src/proactive/engine.py` |
| `process_message` | `@observe(name="job.process_message")` | `src/jobs/router.py` |
| `nightly_batch` | `@observe(name="job.nightly_batch")` | `src/jobs/router.py` |
| `hourly_maintenance` | `@observe(name="job.hourly_maintenance")` | `src/jobs/router.py` |
| `synthesis` | `@observe(name="job.synthesis")` | `src/jobs/router.py` |

Note: `call_model` and `call_tools` in `graph.py` are **not** decorated with `@observe` — the LangChain `CallbackHandler` traces those automatically. Adding `@observe` to LangGraph nodes causes OTEL context detach errors due to TaskGroup async boundaries.

### Trace structure

```
Chat request:
  trace: "chat" (user_id, session_id, tags=["chat"])
  ├─ span: "agent.assemble_context"
  │  └─ span: "embedding" (semantic search, task_type=RETRIEVAL_QUERY)
  ├─ chain: "LangGraph" (via CallbackHandler)
  │  ├─ agent: iteration 0
  │  │  └─ generation: gemini-2.5-flash
  │  ├─ tool: query_graph
  │  │  └─ span: "embedding" (task_type=RETRIEVAL_QUERY)
  │  └─ agent: iteration 1
  │     └─ generation: gemini-2.5-flash (final response)
  └─ (done)

Cold path job:
  trace: "job.process_message" (user_id, tags=["cold_path","job"])
  ├─ span: "cold_path.process"
  │  ├─ span: "cold_path.extraction"
  │  │  └─ generation: gemini-2.5-flash (structured output, thinking_budget=8192)
  │  ├─ span: "embedding" (dedup, task_type=SEMANTIC_SIMILARITY)
  │  └─ span: "embedding.batch" (new nodes, task_type=RETRIEVAL_DOCUMENT)
```

### No-op when unconfigured

If `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, or `LANGFUSE_SECRET_KEY` are empty, all `@observe` decorators become no-ops. No performance overhead, no errors.

## PII Scrubbing (`src/telemetry/pii.py`)

`scrub_pii(text) -> str` — Regex replacement for:
- SSN patterns → `[SSN]`
- Credit card numbers → `[CARD]`
- Email addresses → `[EMAIL]`
- US phone numbers → `[PHONE]`

Used before sending prompt text to Langfuse to prevent PII from reaching external services.

## Trace Flow

```
Request → TraceMiddleware (trace_id) → structlog contextvars
    → @observe creates Langfuse trace with user_id, session_id, tags
    → LangChain CallbackHandler traces agent iterations + LLM calls
    → @observe on cold path/embedding functions creates child spans
    → Errors reported to all 3 sinks
    → flush_langfuse() at stream end
    → Response header: x-trace-id
```

Admin can look up a trace via `GET /admin/trace/{trace_id}` to see all events and LLM usage associated with that request.
