"""Centralized error reporting — logs to structlog, Langfuse, and error_log table."""

import traceback

import structlog

from src.telemetry.langfuse_integration import update_current_observation
from src.telemetry.logger import get_logger

_log = get_logger("errors")


def report_error(
    source: str,
    error: Exception,
    trace_id: str | None = None,
    user_id: str | None = None,
    **extra: object,
) -> None:
    """Report an error to all three sinks. Safe to call from any except block.

    1. structlog with full traceback (→ Railway logs)
    2. Langfuse span level=ERROR (→ Langfuse dashboard)
    3. DB error_log table (→ /admin/errors endpoint)

    DB write is fire-and-forget — if it fails, the error is still in logs and Langfuse.
    """
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    tb_str = "".join(tb)
    error_type = type(error).__name__
    error_message = str(error)

    # 1. structlog — always gets the full traceback
    _log.error(
        source,
        error_type=error_type,
        error_message=error_message,
        trace_id=trace_id,
        user_id=user_id,
        exc_info=True,
        **extra,
    )

    # 2. Langfuse — mark current span as errored
    update_current_observation(
        level="ERROR",
        status_message=f"{error_type}: {error_message}",
    )

    # 3. DB — persist to error_log (fire-and-forget via bound contextvars)
    _persist_error(source, error_type, error_message, tb_str, trace_id, user_id)


def _persist_error(
    source: str,
    error_type: str,
    error_message: str,
    stacktrace: str,
    trace_id: str | None,
    user_id: str | None,
) -> None:
    """Best-effort async persist. Uses structlog contextvars for trace_id if not provided."""
    import asyncio

    ctx = structlog.contextvars.get_contextvars()
    resolved_trace_id = trace_id or ctx.get("trace_id")

    async def _save() -> None:
        try:
            from src.db.supabase import save_error

            await save_error(
                source=source,
                error_type=error_type,
                error_message=error_message,
                stacktrace=stacktrace,
                trace_id=resolved_trace_id,
                user_id=user_id,
            )
        except Exception:
            _log.debug("error_reporting.db_persist_failed", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_save())
    except RuntimeError:
        pass
