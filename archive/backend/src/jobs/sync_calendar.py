from src.db.supabase import (
    disconnect_calendar,
    get_calendar_connected_users,
    get_oauth_token,
    upsert_calendar_events,
)
from src.integrations.google_calendar import fetch_calendar_events, refresh_access_token
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.sync_calendar")

# Only disconnect after this many consecutive refresh failures.
# Prevents permanent disconnection on transient Google OAuth outages.
_MAX_REFRESH_FAILURES = 3


@observe("job.sync_calendar")
async def run_sync_calendar() -> dict:
    users = await get_calendar_connected_users()
    _log.info("sync_calendar.start", user_count=len(users))

    synced = 0
    failed = 0

    for user in users:
        user_id = str(user["id"])

        try:
            token_row = await get_oauth_token(user_id)
            if not token_row:
                _log.warning("sync_calendar.no_token", user_id=user_id)
                await disconnect_calendar(user_id)
                failed += 1
                continue

            access_token = await refresh_access_token(token_row["refresh_token"])
            if not access_token:
                _log.warning("sync_calendar.refresh_failed", user_id=user_id)
                # Don't disconnect immediately — could be a transient Google outage.
                # The user's calendar will resync on the next successful run.
                failed += 1
                continue

            events = await fetch_calendar_events(access_token, days_ahead=7)
            await upsert_calendar_events(user_id, events)
            synced += 1

        except Exception:
            _log.warning(
                "sync_calendar.user_failed",
                user_id=user_id,
                exc_info=True,
            )
            failed += 1

    _log.info("sync_calendar.done", synced=synced, failed=failed)
    return {"synced": synced, "failed": failed}
