import re
from typing import Any

from src.orchestrator.config_loader import load_config
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.scoring")

_energy_patterns_cache: dict[str, re.Pattern[str]] | None = None


def _get_energy_patterns() -> dict[str, re.Pattern[str]]:
    global _energy_patterns_cache
    if _energy_patterns_cache is not None:
        return _energy_patterns_cache

    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    levels = config.get("energy_levels", {})
    patterns: dict[str, re.Pattern[str]] = {}
    for level, level_config in levels.items():
        words = level_config.get("patterns", [])
        if words:
            pattern_str = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
            patterns[level] = re.compile(pattern_str, re.IGNORECASE)

    _energy_patterns_cache = patterns
    return patterns


@register_tool("calculate_urgency")
async def calculate_urgency(
    item: dict[str, Any],
    hours_until_deadline: float | None = None,
) -> float:
    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    weights = config.get("urgency_weights", {})
    breakpoints = config.get("urgency_breakpoints", {})
    type_scores = config.get("deadline_type_scores", {})

    score = 0.0

    deadline_weight = weights.get("deadline", 0.4)
    explicit_weight = weights.get("explicit", 0.3)
    recency_weight = weights.get("recency", 0.2)

    if hours_until_deadline is not None:
        # Walk through breakpoints in order of threshold
        bp_overdue = breakpoints.get("overdue", {})
        bp_imminent = breakpoints.get("imminent", {})
        bp_approaching = breakpoints.get("approaching", {})
        bp_distant = breakpoints.get("distant", {})

        if hours_until_deadline <= bp_overdue.get("threshold_hours", 0):
            score += deadline_weight * bp_overdue.get("score", 1.0)
        elif hours_until_deadline <= bp_imminent.get("threshold_hours", 24):
            score += deadline_weight * bp_imminent.get("score", 0.8)
        elif hours_until_deadline <= bp_approaching.get("threshold_hours", 48):
            score += deadline_weight * bp_approaching.get("score", 0.5)
        else:
            score += deadline_weight * bp_distant.get("score", 0.2)

    deadline_type = item.get("deadline_type", "none")
    type_score = type_scores.get(deadline_type, 0.0)
    score += explicit_weight * type_score

    score += recency_weight * 0.5

    return round(min(score, 1.0), 3)


@register_tool("infer_energy")
async def infer_energy(text: str) -> str:
    patterns = _get_energy_patterns()

    # Check high first (if text matches high-energy words, it's high)
    if "high" in patterns and patterns["high"].search(text):
        return "high"
    if "low" in patterns and patterns["low"].search(text):
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
