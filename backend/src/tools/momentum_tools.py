from typing import Any

from src.db import supabase as db
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.momentum")


@register_tool("check_momentum")
async def check_momentum(user_id: str) -> dict[str, Any]:
    done_count = await db.get_recently_done_count(user_id, hours=24)
    return {
        "done_today": done_count,
        "on_a_roll": done_count >= 3,
    }


@register_tool("pick_next_item")
async def pick_next_item(
    items: list[dict[str, Any]],
    user_id: str,
) -> dict[str, Any] | None:
    if not items:
        return None

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        score = float(item.get("urgency_score", 0.0))

        if item.get("deadline_type") == "hard":
            score += 0.3
        elif item.get("deadline_type") == "soft":
            score += 0.1

        if item.get("energy_estimate") == "low":
            score += 0.15
        elif item.get("energy_estimate") == "medium":
            score += 0.05

        if not item.get("last_surfaced_at"):
            score += 0.1

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]

    _log.info(
        "pick_next.selected",
        user_id=user_id,
        item_id=str(best["id"]),
        score=scored[0][0],
    )

    return best
