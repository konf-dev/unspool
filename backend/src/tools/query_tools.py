import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.db import supabase as db
from src.tools.registry import register_tool
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("tools.query")

_TIMEFRAME_PATTERN = re.compile(r"last_(\d+)_days?")

_TIMEFRAME_MAP: dict[str, int] = {
    "last_week": 7,
    "last_month": 30,
    "last_3_months": 90,
    "last_year": 365,
}


def _parse_timeframe(timeframe: str | None) -> datetime | None:
    if not timeframe:
        return None

    days = _TIMEFRAME_MAP.get(timeframe)
    if days:
        return datetime.now(timezone.utc) - timedelta(days=days)

    match = _TIMEFRAME_PATTERN.match(timeframe)
    if match:
        days = int(match.group(1))
        return datetime.now(timezone.utc) - timedelta(days=days)

    return None


@register_tool("smart_fetch")
@observe("smart_fetch")
async def smart_fetch(
    user_id: str, query_spec: dict[str, Any] | str | None
) -> dict[str, Any]:
    """Dynamically fetch data based on LLM-analyzed query specification.

    query_spec schema (dict):
      search_type: "entity" | "temporal" | "semantic" | "status" | "general"
      entity: str | null
      timeframe: str | null — "last_week", "last_month", "last_N_days"
      sources: list[str] — "items", "memories", "messages", "calendar"
      text_query: str | null
      status_filter: str | null — "open", "done", "all"
      limit: int

    If query_spec is a string (LLM JSON parse failed), falls back to
    a general items search.
    """
    # Handle cases where LLM output_schema parse failed and we got a raw string
    if not isinstance(query_spec, dict):
        _log.warning("smart_fetch.invalid_query_spec", type=type(query_spec).__name__)
        query_spec = {"sources": ["items"], "status_filter": "all", "limit": 10}

    results: dict[str, Any] = {}

    since = _parse_timeframe(query_spec.get("timeframe"))
    entity_name = query_spec.get("entity")
    text_query = query_spec.get("text_query")
    sources = query_spec.get("sources", ["items"])
    status_filter = query_spec.get("status_filter", "all")
    limit = min(query_spec.get("limit", 10), 100)  # cap to prevent excessive fetches

    entity_id = None
    if entity_name:
        entity_id = await db.resolve_entity(user_id, entity_name)
        if not entity_id:
            _log.info(
                "smart_fetch.entity_not_found", entity=entity_name, user_id=user_id
            )

    for source in sources:
        try:
            if source == "items":
                results["items"] = await db.get_items_filtered(
                    user_id=user_id,
                    entity_id=entity_id,
                    since=since,
                    status=status_filter if status_filter != "all" else None,
                    limit=limit,
                )
            elif source == "memories":
                results["memories"] = await db.get_memories_filtered(
                    user_id=user_id,
                    since=since,
                    search_text=text_query,
                    limit=limit,
                )
            elif source == "messages":
                results["messages"] = await db.get_messages_filtered(
                    user_id=user_id,
                    since=since,
                    search_text=text_query or entity_name,
                    limit=limit,
                )
            elif source == "calendar":
                results["calendar"] = await db.get_calendar_events_filtered(
                    user_id=user_id,
                    since=since,
                    limit=limit,
                )
        except Exception:
            _log.warning(
                "smart_fetch.source_failed",
                source=source,
                user_id=user_id,
                exc_info=True,
            )
            results[source] = []

    total = sum(len(v) for v in results.values() if isinstance(v, list))
    _log.info(
        "smart_fetch.done",
        sources=sources,
        total_results=total,
        entity=entity_name,
        timeframe=query_spec.get("timeframe"),
    )
    return results
