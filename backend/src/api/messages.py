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
        from src.db.queries import get_profile, update_profile

        # Check if user was recently active — skip proactive if so.
        # This prevents proactive messages on page refresh, re-login, or fetchLatestPlate.
        should_run_proactive = False
        try:
            profile = await get_profile(user_id)
            if profile:
                last = profile.get("last_interaction_at")
                if last:
                    if isinstance(last, str):
                        last = datetime.fromisoformat(last)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                    should_run_proactive = hours_since >= 1
                else:
                    should_run_proactive = True  # First-ever session
        except Exception:
            pass

        # Mark the user as active BEFORE proactive check
        try:
            await update_profile(user_id, last_interaction_at=datetime.now(timezone.utc))
        except Exception:
            pass

        if should_run_proactive:
            # Evaluate proactive triggers — generates + persists to event_stream.
            try:
                from src.proactive.engine import check_proactive
                await check_proactive(user_id)
            except Exception as e:
                report_error("messages.proactive_failed", e, user_id=user_id)

        # Always deliver queued proactive messages (reminders, nudges) —
        # these are already created by QStash callbacks and should not be
        # gated by the should_run_proactive check.
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
