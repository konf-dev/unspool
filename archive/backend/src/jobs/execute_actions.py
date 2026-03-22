"""Execute pending scheduled actions — nudges, check-ins, reminders.

Safety-net poll runs hourly via consolidated cron. Most actions are delivered
precisely via QStash dispatch_at, but this catches failed dispatches and
actions scheduled >7 days out (QStash free tier max delay).
"""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.execute_actions")

_SEVEN_DAYS_SECONDS = 604800


@observe("job.execute_actions")
async def run_execute_actions() -> dict[str, Any]:
    """Safety-net poll: find and execute all overdue pending actions."""
    pending = await db.get_pending_actions()
    _log.info("execute_actions.start", count=len(pending))

    executed = 0
    failed = 0

    for action in pending:
        action_id = str(action["id"])
        claimed = await db.claim_action(action_id)
        if not claimed:
            continue

        result = await execute_single_action(claimed)
        if result == "executed":
            executed += 1
        elif result == "failed":
            failed += 1

    _log.info("execute_actions.done", executed=executed, failed=failed)
    return {"executed": executed, "failed": failed}


async def execute_single_action(action: dict[str, Any]) -> str:
    """Execute a single action. Expects the action to already be claimed
    (status='executing'). Returns 'executed' or 'failed'."""
    action_id = str(action["id"])
    user_id = str(action["user_id"])
    action_type = action.get("action_type", "nudge")
    payload = action.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

    try:
        await _dispatch_action(user_id, action_type, payload)
        await _record_notification(
            user_id=user_id,
            channel="push" if action_type == "nudge" else "proactive",
            body=payload.get("message", action_type),
            trigger_type=action_type,
            trigger_id=action_id,
        )
        await db.update_action_status(action_id, "executed")

        # Handle recurring: schedule next occurrence and dispatch_at it
        rrule = action.get("rrule")
        if rrule:
            next_at = _next_occurrence(rrule, datetime.now(timezone.utc))
            if next_at:
                new_action = await db.save_scheduled_action(
                    user_id=user_id,
                    action_type=action_type,
                    execute_at=next_at,
                    payload=payload,
                    rrule=rrule,
                )
                delta = (next_at - datetime.now(timezone.utc)).total_seconds()
                if 0 < delta <= _SEVEN_DAYS_SECONDS:
                    from src.integrations.qstash import dispatch_at

                    msg_id = await dispatch_at(
                        "execute-action",
                        {"action_ids": [str(new_action["id"])]},
                        deliver_at=next_at,
                    )
                    if msg_id:
                        await db.mark_action_dispatched(new_action["id"], msg_id)

        return "executed"
    except Exception:
        _log.warning(
            "execute_actions.action_failed",
            action_id=action_id,
            user_id=user_id,
            exc_info=True,
        )
        await db.update_action_status(action_id, "failed")
        return "failed"


async def _dispatch_action(
    user_id: str,
    action_type: str,
    payload: dict[str, Any],
) -> None:
    """Dispatch an action as either a push notification or a proactive message."""
    message = payload.get("message", "")

    if action_type == "nudge":
        subs = await db.get_push_subscriptions(user_id)
        if subs:
            from src.integrations.push import send_push_notification

            body = message or "hey — you asked me to remind you about this"
            for sub in subs:
                await send_push_notification(
                    subscription=sub,
                    title="unspool",
                    body=body,
                    user_id=user_id,
                )
            await _update_last_notification(user_id)
        else:
            await _queue_proactive(user_id, message or "reminder", action_type)

    elif action_type in ("check_in", "ask_question", "surface_item"):
        await _queue_proactive(user_id, message or action_type, action_type)

    else:
        _log.warning("execute_actions.unknown_type", action_type=action_type)
        await _queue_proactive(user_id, message or action_type, action_type)


async def _queue_proactive(
    user_id: str,
    content: str,
    trigger_type: str,
) -> None:
    """Queue a proactive message for delivery on next app open."""
    pool = db.get_pool()
    await pool.execute(
        """
        INSERT INTO proactive_messages (user_id, content, trigger_type, expires_at)
        VALUES ($1, $2, $3, now() + interval '7 days')
        """,
        user_id,
        content,
        trigger_type,
    )


async def _record_notification(
    user_id: str,
    channel: str,
    body: str,
    trigger_type: str,
    trigger_id: str | None = None,
) -> None:
    """Record a notification in history for smart decisions."""
    pool = db.get_pool()
    await pool.execute(
        """
        INSERT INTO notification_history (user_id, channel, body, trigger_type, trigger_id)
        VALUES ($1, $2, $3, $4, $5::uuid)
        """,
        user_id,
        channel,
        body,
        trigger_type,
        trigger_id,
    )


async def _update_last_notification(user_id: str) -> None:
    """Update the user profile with the last notification timestamp."""
    try:
        await db.update_profile(
            user_id, last_notification_at=datetime.now(timezone.utc)
        )
    except Exception:
        _log.warning(
            "execute_actions.update_profile_failed", user_id=user_id, exc_info=True
        )


def _next_occurrence(rrule_str: str, after: datetime) -> datetime | None:
    """Calculate the next occurrence from an RRULE string.

    Uses python-dateutil if available, falls back to simple parsing.
    """
    try:
        from dateutil.rrule import rrulestr

        rule = rrulestr(
            f"DTSTART:{after.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}"
        )
        next_dt = rule.after(after)
        return next_dt
    except ImportError:
        _log.warning("execute_actions.dateutil_not_available")
        return None
    except Exception:
        _log.warning(
            "execute_actions.rrule_parse_failed", rrule=rrule_str, exc_info=True
        )
        return None
