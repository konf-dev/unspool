"""Langfuse integration — auto-instruments OpenAI calls and provides LangChain callback.

Uses langfuse.openai wrapper for all OpenAI calls (completions + embeddings) and
langfuse.langchain.CallbackHandler for LangGraph tracing.  Every OpenAI call made
through our shared client is automatically traced with full input/output/tokens.

No-ops gracefully when Langfuse is not configured.
"""

from typing import Any

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("telemetry.langfuse")

_langfuse_available = False
_callback_handler_cls: Any = None


def _init_langfuse() -> None:
    """Probe whether Langfuse is importable and configured."""
    global _langfuse_available, _callback_handler_cls
    settings = get_settings()
    if not (
        settings.LANGFUSE_HOST
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    ):
        return

    try:
        # Set env vars so langfuse auto-configures from environment
        import os
        os.environ.setdefault("LANGFUSE_HOST", settings.LANGFUSE_HOST)
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)

        from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
        _callback_handler_cls = CallbackHandler
        _langfuse_available = True
        _log.info("langfuse.initialized", host=settings.LANGFUSE_HOST)
    except Exception as e:
        _log.warning("langfuse.import_failed", error=str(e), error_type=type(e).__name__)


def is_langfuse_available() -> bool:
    return _langfuse_available


def get_langchain_handler(
    trace_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Create a Langfuse CallbackHandler for LangGraph/LangChain.

    Returns None if Langfuse is not configured.  Pass this handler to
    LangGraph's ``astream()`` or ``ainvoke()`` via the ``config`` dict::

        config = {"callbacks": [handler]} if handler else {}
        async for event in app.astream(state, stream_mode="updates", config=config):
            ...
    """
    if not _langfuse_available or _callback_handler_cls is None:
        return None

    try:
        settings = get_settings()
        handler = _callback_handler_cls(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            trace_name=f"chat:{trace_id[:8]}" if trace_id else "chat",
            user_id=user_id,
            session_id=session_id,
            tags=tags or ["chat"],
            metadata=metadata or {},
        )
        if trace_id:
            handler.trace_id = trace_id
        return handler
    except Exception:
        _log.debug("langfuse.handler_creation_failed", exc_info=True)
        return None


def flush_langfuse() -> None:
    """Flush any pending Langfuse events.  Safe to call even when unconfigured."""
    if not _langfuse_available:
        return
    try:
        from langfuse import get_client  # type: ignore[import-untyped]
        client = get_client()
        if client:
            client.flush()
    except Exception:
        pass


# ──────── Backwards-compatible no-op helpers (used in proactive/context) ───

def observe(name: str | None = None, **kwargs: Any) -> Any:
    """Decorator — currently a no-op.  Tracing is done via CallbackHandler."""
    def decorator(fn: Any) -> Any:
        return fn
    return decorator


def update_current_observation(**kwargs: Any) -> None:
    """No-op.  Observation updates happen through the CallbackHandler automatically."""
    pass


def update_current_trace(**kwargs: Any) -> None:
    """No-op.  Trace metadata is set when creating the CallbackHandler."""
    pass


# Initialize on import
_init_langfuse()
