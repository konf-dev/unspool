"""Langfuse integration — thin wrapper that no-ops when Langfuse is not configured."""

from typing import Any

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("telemetry.langfuse")

_langfuse_available = False
_observe_fn: Any = None


def _init_langfuse() -> None:
    global _langfuse_available, _observe_fn
    settings = get_settings()
    if not (
        settings.LANGFUSE_HOST
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    ):
        return

    try:
        from langfuse.decorators import observe  # type: ignore[import-untyped]

        _observe_fn = observe
        _langfuse_available = True
        _log.info("langfuse.initialized", host=settings.LANGFUSE_HOST)
    except ImportError:
        _log.warning("langfuse.import_failed")


def observe(name: str | None = None, **kwargs: Any) -> Any:
    """Decorator that wraps langfuse.decorators.observe when available, else no-ops."""

    def decorator(fn: Any) -> Any:
        if _langfuse_available and _observe_fn is not None:
            return _observe_fn(name=name, **kwargs)(fn)
        return fn

    return decorator


def observe_generation(name: str | None = None, **kwargs: Any) -> Any:
    """Decorator for LLM generation steps — uses as_type='generation'."""
    return observe(name=name, as_type="generation", **kwargs)


def get_langfuse_context() -> Any:
    """Get langfuse_context for manual span/trace operations."""
    if not _langfuse_available:
        return None
    try:
        from langfuse.decorators import langfuse_context  # type: ignore[import-untyped]

        return langfuse_context
    except ImportError:
        return None


def update_current_observation(**kwargs: Any) -> None:
    """Update the current Langfuse observation. No-ops when unconfigured."""
    if not _langfuse_available:
        return
    try:
        from langfuse.decorators import langfuse_context  # type: ignore[import-untyped]

        langfuse_context.update_current_observation(**kwargs)
    except Exception:
        _log.debug("langfuse.update_observation_failed", exc_info=True)


def update_current_trace(**kwargs: Any) -> None:
    """Update the current Langfuse trace."""
    if not _langfuse_available:
        return
    try:
        from langfuse.decorators import langfuse_context  # type: ignore[import-untyped]

        langfuse_context.update_current_trace(**kwargs)
    except Exception:
        _log.debug("langfuse.update_trace_failed", exc_info=True)


# Initialize on import
_init_langfuse()
