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
2. **Langfuse** — Marks current observation as ERROR (if configured)
3. **DB error_log** — Fire-and-forget async persist (won't crash caller if DB fails)

The DB persist resolves `trace_id` from structlog contextvars if not provided.

## Langfuse Integration (`src/telemetry/langfuse_integration.py`)

Thin wrapper that no-ops when Langfuse is not configured.

- `@observe(name)` — Decorator, wraps `langfuse.decorators.observe`
- `@observe_generation(name)` — Same with `as_type="generation"`
- `update_current_observation(**kwargs)` — Update current span
- `update_current_trace(**kwargs)` — Update current trace
- `get_langfuse_context()` — Access raw langfuse_context

All functions silently no-op if `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, or `LANGFUSE_SECRET_KEY` are not set.

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
    → Handler logs with trace_id auto-attached
    → Langfuse trace created with user_id, session_id
    → Tool calls logged as spans
    → Errors reported to all 3 sinks
    → Response header: x-trace-id
```

Admin can look up a trace via `GET /admin/trace/{trace_id}` to see all events and LLM usage associated with that request.
