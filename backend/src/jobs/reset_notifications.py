from src.db.supabase import _get_pool
from src.telemetry.logger import get_logger

_log = get_logger("jobs.reset_notifications")


async def run_reset_notifications() -> dict:
    pool = _get_pool()
    row = await pool.fetchrow(
        "WITH updated AS ("
        "  UPDATE user_profiles SET notification_sent_today = false "
        "  WHERE notification_sent_today = true "
        "  RETURNING id"
        ") SELECT COUNT(*) AS cnt FROM updated"
    )
    count = int(row["cnt"]) if row else 0
    _log.info("reset_notifications.done", reset_count=count)
    return {"reset": count}
