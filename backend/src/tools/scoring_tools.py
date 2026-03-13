import re
from typing import Any

from src.orchestrator.config_loader import load_config
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.scoring")

_HIGH_ENERGY_PATTERNS = re.compile(
    r"\b(write|build|create|design|plan|organize|move|clean|exercise)\b", re.IGNORECASE
)
_LOW_ENERGY_PATTERNS = re.compile(
    r"\b(text|email|call|reply|check|read|look up|remind)\b", re.IGNORECASE
)


@register_tool("calculate_urgency")
async def calculate_urgency(
    item: dict[str, Any],
    hours_until_deadline: float | None = None,
) -> float:
    try:
        weights = load_config("scoring").get("urgency_weights", {})
    except FileNotFoundError:
        weights = {}

    score = 0.0

    deadline_weight = weights.get("deadline", 0.4)
    explicit_weight = weights.get("explicit", 0.3)
    recency_weight = weights.get("recency", 0.2)
    _dependency_weight = weights.get("dependency", 0.1)

    if hours_until_deadline is not None:
        if hours_until_deadline <= 0:
            score += deadline_weight * 1.0
        elif hours_until_deadline <= 24:
            score += deadline_weight * 0.8
        elif hours_until_deadline <= 48:
            score += deadline_weight * 0.5
        else:
            score += deadline_weight * 0.2

    if item.get("deadline_type") == "hard":
        score += explicit_weight * 0.8
    elif item.get("deadline_type") == "soft":
        score += explicit_weight * 0.4

    score += recency_weight * 0.5

    return round(min(score, 1.0), 3)


@register_tool("infer_energy")
async def infer_energy(text: str) -> str:
    if _HIGH_ENERGY_PATTERNS.search(text):
        return "high"
    if _LOW_ENERGY_PATTERNS.search(text):
        return "low"
    return "medium"


@register_tool("enrich_items")
async def enrich_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        if not item.get("energy_estimate"):
            item["energy_estimate"] = await infer_energy(
                item.get("raw_text", "") or item.get("interpreted_action", "")
            )
        if not item.get("urgency_score"):
            item["urgency_score"] = await calculate_urgency(item)
    return items
