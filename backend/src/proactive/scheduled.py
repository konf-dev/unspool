"""Scheduled action creation with rrule support."""

from datetime import datetime
from typing import Any

from src.db.queries import save_scheduled_action, mark_action_dispatched
from src.telemetry.logger import get_logger

_log = get_logger("proactive.scheduled")

_SEVEN_DAYS_SECONDS = 604800


async def create_scheduled_action(
    user_id: str,
    action_type: str,
    execute_at: datetime,
    payload: dict[str, Any] | None = None,
    rrule: str | None = None,
) -> dict[str, Any]:
    """Create a scheduled action and dispatch via QStash if within 7 days."""
    action = await save_scheduled_action(
        user_id=user_id,
        action_type=action_type,
        execute_at=execute_at,
        payload=payload,
        rrule=rrule,
    )

    from datetime import timezone
    delta = (execute_at - datetime.now(timezone.utc)).total_seconds()
    if 0 < delta <= _SEVEN_DAYS_SECONDS:
        from src.integrations.qstash import dispatch_at
        msg_id = await dispatch_at(
            "execute-action",
            {"action_ids": [action["id"]]},
            deliver_at=execute_at,
        )
        if msg_id:
            await mark_action_dispatched(action["id"], msg_id)
            _log.info("scheduled.dispatched", action_id=action["id"], msg_id=msg_id)

    return action
