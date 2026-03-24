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

Uses langfuse v4's real `@observe` decorator with OpenTelemetry context propagation. The `langfuse.openai` wrapper auto-instruments all OpenAI calls. When called inside an `@observe` scope, all LLM calls nest under the parent trace automatically.

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

1. `@observe(name="chat")` on the root function creates an OTEL span → becomes the Langfuse trace
2. `propagate_trace_attributes(user_id=..., session_id=..., tags=...)` sets trace metadata
3. Nested `@observe` calls (e.g., `hot_path.call_model`) create child spans automatically
4. `langfuse.openai.AsyncOpenAI` wrapper auto-creates generation spans under the active observe scope
5. `CallbackHandler()` created inside an observe scope inherits the OTEL context — all LangGraph spans nest

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

### Trace structure

```
Chat request:
  trace: "chat" (user_id, session_id, tags=["chat"])
  ├─ span: "agent.assemble_context"
  │  └─ generation: OpenAI embedding (semantic search)
  ├─ chain: "LangGraph"
  │  ├─ agent: "agent"
  │  │  ├─ span: "hot_path.call_model"
  │  │  │  └─ generation: OpenAI gpt-4.1
  │  │  └─ span: "hot_path.call_tools"
  │  │     └─ generation: OpenAI embedding (query_graph search)
  │  └─ chain: "route_logic"
  └─ generation: OpenAI gpt-4.1 (final response)

Cold path job:
  trace: "job.process_message" (user_id, tags=["cold_path","job"], meta={parent_chat_trace_id})
  ├─ span: "cold_path.process"
  │  ├─ span: "cold_path.extraction"
  │  │  └─ generation: OpenAI gpt-4.1 (structured output)
  │  ├─ span: "embedding" (dedup search 1)
  │  └─ span: "embedding" (dedup search 2)
```

### No-op when unconfigured

If `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, or `LANGFUSE_SECRET_KEY` are empty, all `@observe` decorators become no-ops. No performance overhead, no errors. The OpenAI client falls back to plain `openai.AsyncOpenAI` (no instrumentation).

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
    → Nested @observe calls create child spans
    → langfuse.openai wrapper auto-traces OpenAI calls
    → LangChain CallbackHandler traces agent iterations
    → Errors reported to all 3 sinks
    → flush_langfuse() at stream end
    → Response header: x-trace-id
```

Admin can look up a trace via `GET /admin/trace/{trace_id}` to see all events and LLM usage associated with that request.
