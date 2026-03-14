from collections.abc import Callable
from typing import Any

from src.orchestrator.config_loader import load_config
from src.orchestrator.types import Context
from src.tools.context_tools import (
    fetch_calendar_events,
    fetch_entities,
    fetch_items,
    fetch_memories,
    fetch_messages,
    fetch_profile,
    fetch_urgent_items,
)
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.context")

_LOADERS: dict[str, Callable[..., Any]] = {
    "profile": fetch_profile,
    "recent_messages": fetch_messages,
    "open_items": fetch_items,
    "urgent_items": fetch_urgent_items,
    "entities": fetch_entities,
    "memories": fetch_memories,
    "calendar_events": fetch_calendar_events,
}

# Extra kwargs to pass to loaders based on config defaults.
# Loaders not listed here are called with just (user_id,).
_LOADER_KWARGS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "recent_messages": lambda d: {"limit": d.get("recent_messages_limit", 20)},
    "open_items": lambda d: {"limit": d.get("open_items_limit", 50)},
    "memories": lambda d: {"limit": d.get("memories_limit", 5)},
}


async def assemble_context(
    user_id: str,
    trace_id: str,
    message: str,
    intent: str,
) -> Context:
    context_rules = load_config("context_rules")
    defaults = context_rules.get("defaults", {})

    rule = context_rules.get("rules", {}).get(intent, {})
    required = rule.get("load", [])
    optional = rule.get("optional", [])

    all_fields = set(required + optional)

    ctx = Context(user_id=user_id, trace_id=trace_id, user_message=message)

    for field in all_fields:
        loader = _LOADERS.get(field)
        if not loader:
            _log.warning("context.unknown_field", field=field, intent=intent)
            continue

        try:
            kwargs_fn = _LOADER_KWARGS.get(field)
            extra_kwargs = kwargs_fn(defaults) if kwargs_fn else {}
            result = await loader(user_id, **extra_kwargs)
            setattr(ctx, field, result)
        except Exception:
            if field in required:
                _log.error("context.required_field_failed", field=field, intent=intent)
                raise
            _log.warning("context.optional_field_failed", field=field, intent=intent)

    _log.info(
        "context.assembled",
        trace_id=trace_id,
        intent=intent,
        fields_loaded=list(all_fields),
    )
    return ctx
