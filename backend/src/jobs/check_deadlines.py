"""Check for approaching deadlines and send push notifications."""

from datetime import datetime, timezone

from src.core.config_loader import load_config
from src.db.queries import get_active_users, get_profile, get_push_subscriptions, update_profile, get_proactive_items
from src.telemetry.logger import get_logger

_log = get_logger("jobs.check_deadlines")


def _in_quiet_hours(tz_name: str | None, start: int, end: int) -> bool:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (KeyError, TypeError):
        tz = timezone.utc

    local_hour = datetime.now(tz).hour
    if start <= end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


async def run_check_deadlines() -> dict:
    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    notif_config = config.get("notifications", {})
    quiet_start = notif_config.get("quiet_hours_start", 1)
    quiet_end = notif_config.get("quiet_hours_end", 7)
    deadline_hours = notif_config.get("deadline_window_hours", 24)
    title = notif_config.get("title", "unspool")
    body_single = notif_config.get("body_single", "Deadline approaching: {action}")
    body_multiple = notif_config.get("body_multiple", "You have {count} items with deadlines in the next {hours} hours")

    users = await get_active_users(days=30)
    _log.info("check_deadlines.start", user_count=len(users))

    notified = 0
    skipped = 0

    for user in users:
        user_id = user["id"]
        try:
            profile = await get_profile(user_id)
            if not profile:
                continue

            tz_name = profile.get("timezone")
            if profile.get("notification_sent_today"):
                skipped += 1
                continue

            if _in_quiet_hours(tz_name, quiet_start, quiet_end):
                skipped += 1
                continue

            items = await get_proactive_items(user_id, hours=deadline_hours)
            if not items:
                continue

            if len(items) == 1:
                body = body_single.format(action=items[0].get("content", "upcoming deadline"))
            else:
                body = body_multiple.format(count=len(items), hours=deadline_hours)

            # Push notification (if subscribed)
            subscriptions = await get_push_subscriptions(user_id)
            if subscriptions:
                from src.integrations.push import send_push_notification
                for sub in subscriptions:
                    await send_push_notification(subscription=sub, title=title, body=body, user_id=user_id)

            # Always save as in-app message so it shows on next open
            from src.db.queries import save_proactive_message
            await save_proactive_message(user_id, body, "deadline_imminent")

            await update_profile(user_id, notification_sent_today=True)

            notified += 1
        except Exception:
            _log.warning("check_deadlines.user_failed", user_id=user_id, exc_info=True)
            skipped += 1

    _log.info("check_deadlines.done", notified=notified, skipped=skipped)
    return {"notified": notified, "skipped": skipped}
