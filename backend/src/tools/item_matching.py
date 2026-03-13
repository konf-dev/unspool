from typing import Any

from src.db import supabase as db
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.item_matching")


def _text_similarity(query: str, candidate: str) -> float:
    query_words = set(query.lower().split())
    candidate_words = set(candidate.lower().split())
    if not query_words or not candidate_words:
        return 0.0
    intersection = query_words & candidate_words
    union = query_words | candidate_words
    return len(intersection) / len(union)


@register_tool("fuzzy_match_item")
async def fuzzy_match_item(
    user_id: str,
    text: str,
) -> dict[str, Any] | None:
    items = await db.get_open_items(user_id)
    if not items:
        return None

    best_score = 0.0
    best_item: dict[str, Any] | None = None

    for item in items:
        action = item.get("interpreted_action", "")
        raw = item.get("raw_text", "")
        score = max(
            _text_similarity(text, action),
            _text_similarity(text, raw),
        )
        if text.lower() in action.lower() or text.lower() in raw.lower():
            score = max(score, 0.7)
        if score > best_score:
            best_score = score
            best_item = item

    if best_score < 0.1:
        _log.info("fuzzy_match.no_match", user_id=user_id, query=text[:50])
        return None

    _log.info(
        "fuzzy_match.found",
        user_id=user_id,
        score=best_score,
        item_id=str(best_item["id"]) if best_item else None,
    )
    return best_item


@register_tool("reschedule_item")
async def reschedule_item(
    item: dict[str, Any] | None,
    user_id: str,
) -> dict[str, Any] | None:
    if not item:
        return None

    from datetime import datetime, timedelta, timezone

    item_id = str(item["id"])
    current_urgency = float(item.get("urgency_score", 0.0))
    new_urgency = round(current_urgency * 0.7, 3)
    nudge_after = datetime.now(timezone.utc) + timedelta(days=2)

    result = await db.update_item(
        item_id,
        urgency_score=new_urgency,
        nudge_after=nudge_after,
    )

    await db.save_item_event(
        item_id=item_id,
        user_id=user_id,
        event_type="rescheduled",
    )

    return result
