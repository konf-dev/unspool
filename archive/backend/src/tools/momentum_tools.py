from typing import Any

from src.db import supabase as db
from src.config_loader import load_config
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.momentum")


@register_tool("check_momentum")
async def check_momentum(user_id: str) -> dict[str, Any]:
    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    momentum_config = config.get("momentum", {})
    lookback_hours = momentum_config.get("lookback_hours", 24)
    threshold = momentum_config.get("on_a_roll_threshold", 3)

    done_count = await db.get_recently_done_count(user_id, hours=lookback_hours)
    return {
        "done_today": done_count,
        "on_a_roll": done_count >= threshold,
    }


@register_tool("pick_next_item")
async def pick_next_item(
    items: list[dict[str, Any]] | None,
    user_id: str,
) -> dict[str, Any]:
    if not items or not isinstance(items, list):
        return {"status": "no_items_found"}

    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    pick_config = config.get("pick_next", {})
    boost_hard = pick_config.get("boost_hard_deadline", 0.3)
    boost_soft = pick_config.get("boost_soft_deadline", 0.1)
    boost_low_energy = pick_config.get("boost_low_energy", 0.15)
    boost_med_energy = pick_config.get("boost_medium_energy", 0.05)
    boost_never_surfaced = pick_config.get("boost_never_surfaced", 0.1)

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        score = float(item.get("urgency_score", 0.0))

        if item.get("deadline_type") == "hard":
            score += boost_hard
        elif item.get("deadline_type") == "soft":
            score += boost_soft

        if item.get("energy_estimate") == "low":
            score += boost_low_energy
        elif item.get("energy_estimate") == "medium":
            score += boost_med_energy

        if not item.get("last_surfaced_at"):
            score += boost_never_surfaced

        scored.append((score, item))

    if not scored:
        return {"status": "no_items_found"}

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    best["status"] = "success"

    _log.info(
        "pick_next.selected",
        user_id=user_id,
        item_id=str(best.get("id", "unknown")),
        score=scored[0][0],
    )

    return best
