from typing import Any

from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.scoring")


@register_tool("enrich_items")
async def enrich_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in missing energy_estimate and urgency_score with sensible defaults.

    The LLM extract prompt is expected to set these values. This tool only
    provides defaults when the LLM returned null — it does NOT override
    LLM decisions with heuristics.
    """
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("items", [])
    if not isinstance(items, list):
        _log.warning("enrich_items.invalid_input", type=type(items).__name__)
        return []
    for item in items:
        if not item.get("energy_estimate"):
            item["energy_estimate"] = "medium"
        if item.get("urgency_score") is None:
            item["urgency_score"] = _default_urgency(item)
    return items


def _default_urgency(item: dict[str, Any]) -> float:
    """Simple default urgency based on deadline type. Used only when the LLM
    didn't provide a score. The decay_urgency cron job recalculates properly."""
    deadline_type = item.get("deadline_type", "none")
    if deadline_type == "hard":
        return 0.5
    if deadline_type == "soft":
        return 0.3
    return 0.1
