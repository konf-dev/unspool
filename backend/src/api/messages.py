from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth.supabase_auth import get_current_user
from src.db import supabase as db
from src.telemetry.logger import get_logger

_log = get_logger("api.messages")

router = APIRouter()


def _serialize_message(msg: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in msg.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


async def _check_proactive(user_id: str) -> dict[str, Any] | None:
    deadline_items = await db.get_proactive_items(user_id, hours=24)
    if deadline_items:
        count = len(deadline_items)
        soonest = deadline_items[0]
        action = soonest.get("interpreted_action", "something")
        content = (
            f"Hey — heads up, you've got {action} coming up soon."
            if count == 1
            else f"Hey — you've got {count} things with deadlines in the next 24 hours. "
            f"The most urgent is {action}."
        )
        msg = await db.save_message(
            user_id=user_id,
            role="assistant",
            content=content,
            metadata={"type": "proactive", "trigger": "deadline"},
        )
        return msg

    last_interaction = await db.get_last_interaction(user_id)
    if last_interaction:
        try:
            last_dt = datetime.fromisoformat(last_interaction)
            now = datetime.now(timezone.utc)
            days_absent = (now - last_dt).days
            if days_absent >= 3:
                content = (
                    "Hey, welcome back! Everything's still here, "
                    "nothing to catch up on. What's on your mind?"
                )
                msg = await db.save_message(
                    user_id=user_id,
                    role="assistant",
                    content=content,
                    metadata={"type": "proactive", "trigger": "absence"},
                )
                return msg
        except (ValueError, TypeError):
            pass

    return None


@router.get("/messages")
async def get_messages(
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict[str, Any]:
    is_initial_load = before is None

    if is_initial_load:
        proactive_msg = await _check_proactive(user_id)
        if proactive_msg:
            _log.info("messages.proactive_sent", user_id=user_id)

    messages = await db.get_messages(user_id, limit=limit, before_id=before)
    serialized = [_serialize_message(m) for m in messages]

    return {
        "messages": serialized,
        "has_more": len(messages) == limit,
    }
