"""GET /api/messages — paginated message history with proactive injection."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth.supabase_auth import get_current_user
from src.core.database import AsyncSessionLocal
from src.db.queries import get_messages_from_events
from src.telemetry.error_reporting import report_error
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


@router.get("/messages")
async def get_messages(
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict[str, Any]:
    is_initial_load = before is None

    if is_initial_load:
        # Evaluate proactive triggers — generates + persists to event_stream.
        # We await fully so the message is committed before the fetch below.
        try:
            from src.proactive.engine import check_proactive
            await check_proactive(user_id)
        except Exception as e:
            report_error("messages.proactive_failed", e, user_id=user_id)

        # Deliver queued proactive messages — persist to event_stream then mark delivered
        try:
            from src.db.queries import (
                get_unconsumed_proactive_messages,
                mark_proactive_messages_delivered,
                append_message_event,
            )
            queued = await get_unconsumed_proactive_messages(user_id)
            if queued:
                ids = [q["id"] for q in queued]
                async with AsyncSessionLocal() as sess:
                    for q in queued:
                        await append_message_event(
                            sess, user_id, "assistant", q["content"],
                            metadata={"type": "proactive", "trigger": q["trigger_type"], "is_queued": True},
                        )
                    await sess.commit()
                await mark_proactive_messages_delivered(user_id, ids)
                _log.info("messages.queued_proactive_delivered", count=len(queued), user_id=user_id)
        except Exception as e:
            report_error("messages.queued_proactive_failed", e, user_id=user_id)

    # Fetch messages — proactive + queued messages are already committed to event_stream
    async with AsyncSessionLocal() as session:
        messages = await get_messages_from_events(session, user_id, limit=limit, before=before)

    serialized = [_serialize_message(m) for m in messages]

    return {
        "messages": serialized,
        "has_more": len(messages) == limit,
    }
