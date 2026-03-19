from datetime import datetime, timezone

from src.db.supabase import (
    get_push_subscriptions,
    get_users_with_urgent_deadlines,
    update_profile,
)
from src.integrations.push import send_push_notification
from src.config_loader import load_config
from src.telemetry.langfuse_integration import observe
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
        # Same-day range (e.g., 1am-7am)
        return start <= local_hour < end
    # Wrap-around midnight (e.g., 22pm-7am)
    return local_hour >= start or local_hour < end


@observe("job.check_deadlines")
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
    body_single_template = notif_config.get(
        "body_single", "Deadline approaching: {action}"
    )
    body_multiple_template = notif_config.get(
        "body_multiple",
        "You have {count} items with deadlines in the next {hours} hours",
    )

    users = await get_users_with_urgent_deadlines(hours=deadline_hours)
    _log.info("check_deadlines.start", user_count=len(users))

    notified = 0
    skipped = 0

    grouped: dict[str, list[dict]] = {}
    for row in users:
        uid = str(row["user_id"])
        grouped.setdefault(uid, []).append(row)

    for user_id, items in grouped.items():
        try:
            tz_name = items[0].get("timezone")
            if items[0].get("notification_sent_today"):
                skipped += 1
                continue

            if _in_quiet_hours(tz_name, quiet_start, quiet_end):
                skipped += 1
                continue

            try:
                await update_profile(user_id, notification_sent_today=True)
            except ValueError:
                skipped += 1
                continue

            subscriptions = await get_push_subscriptions(user_id)
            if not subscriptions:
                continue

            if len(items) == 1:
                action = items[0].get("interpreted_action", "upcoming deadline")
                body = body_single_template.format(action=action)
            else:
                body = body_multiple_template.format(
                    count=len(items), hours=deadline_hours
                )

            for sub in subscriptions:
                await send_push_notification(
                    subscription=sub,
                    title=title,
                    body=body,
                    user_id=user_id,
                )

            notified += 1
        except Exception:
            _log.warning("check_deadlines.user_failed", user_id=user_id, exc_info=True)
            skipped += 1

    _log.info("check_deadlines.done", notified=notified, skipped=skipped)
    return {"notified": notified, "skipped": skipped}
