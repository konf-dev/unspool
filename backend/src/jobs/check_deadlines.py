from datetime import datetime, timezone

from src.db.supabase import (
    get_push_subscriptions,
    get_users_with_urgent_deadlines,
    update_profile,
)
from src.integrations.push import send_push_notification
from src.telemetry.logger import get_logger

_log = get_logger("jobs.check_deadlines")

_QUIET_HOUR_START = 1
_QUIET_HOUR_END = 7


def _in_quiet_hours(tz_name: str | None) -> bool:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (KeyError, TypeError):
        tz = timezone.utc

    local_hour = datetime.now(tz).hour
    return _QUIET_HOUR_START <= local_hour < _QUIET_HOUR_END


async def run_check_deadlines() -> dict:
    users = await get_users_with_urgent_deadlines(hours=24)
    _log.info("check_deadlines.start", user_count=len(users))

    notified = 0
    skipped = 0

    grouped: dict[str, list[dict]] = {}
    for row in users:
        uid = str(row["user_id"])
        grouped.setdefault(uid, []).append(row)

    for user_id, items in grouped.items():
        tz_name = items[0].get("timezone")
        if items[0].get("notification_sent_today"):
            skipped += 1
            continue

        if _in_quiet_hours(tz_name):
            skipped += 1
            continue

        # Atomic: claim notification slot before sending
        try:
            await update_profile(user_id, notification_sent_today=True)
        except ValueError:
            skipped += 1
            continue

        subscriptions = await get_push_subscriptions(user_id)
        if not subscriptions:
            continue

        if len(items) == 1:
            body = f"Deadline approaching: {items[0]['interpreted_action']}"
        else:
            body = f"You have {len(items)} items with deadlines in the next 24 hours"

        for sub in subscriptions:
            await send_push_notification(
                subscription=sub,
                title="Unspool — Deadline Alert",
                body=body,
                user_id=user_id,
            )

        notified += 1

    _log.info("check_deadlines.done", notified=notified, skipped=skipped)
    return {"notified": notified, "skipped": skipped}
