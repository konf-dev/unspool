"""Execute pending scheduled actions — nudges, check-ins, reminders."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import queries as db
from src.telemetry.logger import get_logger

_log = get_logger("jobs.execute_actions")

_SEVEN_DAYS_SECONDS = 604800


async def run_execute_actions() -> dict[str, Any]:
    pending = await db.get_pending_actions()
    _log.info("execute_actions.start", count=len(pending))

    executed = 0
    failed = 0

    for action in pending:
        action_id = action["id"]
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
    action_id = action["id"]
    user_id = action["user_id"]
    action_type = action.get("action_type", "nudge")
    payload = action.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

    try:
        await _dispatch_action(user_id, action_type, payload)
        await db.update_action_status(action_id, "executed")

        # Handle recurring via rrule
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
                        {"action_ids": [new_action["id"]]},
                        deliver_at=next_at,
                    )
                    if msg_id:
                        await db.mark_action_dispatched(new_action["id"], msg_id)

        return "executed"
    except Exception:
        _log.warning("execute_actions.action_failed", action_id=action_id, exc_info=True)
        await db.update_action_status(action_id, "failed")
        return "failed"


async def _dispatch_action(user_id: str, action_type: str, payload: dict[str, Any]) -> None:
    message = payload.get("message", "")

    if action_type == "nudge":
        subs = await db.get_push_subscriptions(user_id)
        if subs:
            from src.integrations.push import send_push_notification
            body = message or "hey — you asked me to remind you about this"
            for sub in subs:
                await send_push_notification(subscription=sub, title="unspool", body=body, user_id=user_id)
        else:
            await db.save_proactive_message(user_id, message or "reminder", action_type)
    else:
        await db.save_proactive_message(user_id, message or action_type, action_type)


def _next_occurrence(rrule_str: str, after: datetime) -> datetime | None:
    try:
        from dateutil.rrule import rrulestr
        rule = rrulestr(f"DTSTART:{after.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}")
        return rule.after(after)
    except ImportError:
        _log.warning("execute_actions.dateutil_not_available")
        return None
    except Exception:
        _log.warning("execute_actions.rrule_parse_failed", rrule=rrule_str, exc_info=True)
        return None
