"""Langfuse integration — real @observe decorator + OpenTelemetry context propagation.

Uses langfuse v4's @observe decorator for creating trace hierarchies via OTEL.
The langfuse.openai wrapper auto-nests under any active @observe scope.
The LangChain CallbackHandler auto-nests when created within an @observe scope.

No-ops gracefully when Langfuse is not configured.
"""

from typing import Any

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("telemetry.langfuse")

_langfuse_available = False


def _init_langfuse() -> None:
    """Probe whether Langfuse is importable and configured."""
    global _langfuse_available
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

        # Verify imports work
        from langfuse import observe as _obs, get_client as _gc, propagate_attributes as _pa  # noqa: F401
        from langfuse.langchain import CallbackHandler as _ch  # noqa: F401

        _langfuse_available = True
        _log.info("langfuse.initialized", host=settings.LANGFUSE_HOST)
    except Exception as e:
        _log.warning("langfuse.import_failed", error=str(e), error_type=type(e).__name__)


def is_langfuse_available() -> bool:
    return _langfuse_available


# ──────── @observe: real decorator or no-op ────────

if False:
    # Type stub — replaced at module init time
    pass


def _noop_observe(name: str | None = None, **kwargs: Any) -> Any:
    """No-op decorator fallback when Langfuse is unavailable."""
    def decorator(fn: Any) -> Any:
        return fn
    if callable(name):
        return name
    return decorator


def _get_observe():
    """Return the real or no-op observe decorator."""
    if _langfuse_available:
        from langfuse import observe as _real_observe
        return _real_observe
    return _noop_observe


# Lazy property — resolved after _init_langfuse()
class _ObserveProxy:
    """Proxy that resolves to real @observe or no-op depending on availability."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _get_observe()(*args, **kwargs)

    def __repr__(self) -> str:
        return f"observe(langfuse={'enabled' if _langfuse_available else 'disabled'})"


observe = _ObserveProxy()


# ──────── propagate_attributes: set user_id, session_id, tags on trace ────────

def propagate_trace_attributes(
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> Any:
    """Context manager to propagate trace-level attributes to all child spans.

    Use inside an @observe-decorated function to set user_id, session_id, tags
    on the current trace and all nested spans.

    Returns a context manager (sync or async).  No-ops when Langfuse is unavailable.
    """
    if _langfuse_available:
        from langfuse import propagate_attributes
        return propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            tags=tags,
            metadata=metadata,
        )

    # No-op context manager
    from contextlib import nullcontext
    return nullcontext()


# ──────── update_current_observation / update_current_trace ────────

def update_current_observation(**kwargs: Any) -> None:
    """Update the current active span with metadata/output/etc."""
    if not _langfuse_available:
        return
    try:
        from langfuse import get_client
        client = get_client()
        client.update_current_span(**kwargs)
    except Exception:
        _log.debug("langfuse.update_observation_failed", exc_info=True)


def update_current_trace(**kwargs: Any) -> None:
    """Deprecated — use propagate_trace_attributes() instead.

    Kept for backwards compatibility with proactive/engine.py.
    Maps to update_current_span for metadata/output updates.
    """
    update_current_observation(**kwargs)


# ──────── LangChain callback handler from context ────────

def get_langchain_handler_from_context() -> Any | None:
    """Create a LangChain CallbackHandler that inherits the current @observe trace context.

    When created within an @observe scope, all LangChain spans will nest
    under the current trace.  Returns None if Langfuse is unavailable.
    """
    if not _langfuse_available:
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:
        _log.debug("langfuse.handler_from_context_failed", exc_info=True)
        return None


# ──────── Flush ────────

def flush_langfuse() -> None:
    """Flush any pending Langfuse events.  Safe to call even when unconfigured."""
    if not _langfuse_available:
        return
    try:
        from langfuse import get_client
        client = get_client()
        if client:
            client.flush()
    except Exception:
        pass


# Initialize on import
_init_langfuse()
