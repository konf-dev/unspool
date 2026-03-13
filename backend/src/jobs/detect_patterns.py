import json

from src.db.supabase import get_active_users, get_completion_stats, update_profile
from src.telemetry.logger import get_logger

_log = get_logger("jobs.detect_patterns")


async def run_detect_patterns() -> dict:
    users = await get_active_users(days=30)
    _log.info("detect_patterns.start", user_count=len(users))

    updated = 0
    for user in users:
        user_id = str(user["id"])
        stats = await get_completion_stats(user_id)

        patterns = {
            "completions_by_dow": stats.get("completions_by_dow", {}),
            "total_completed": stats.get("total_completed", 0),
            "avg_daily": stats.get("avg_daily", 0.0),
        }

        await update_profile(user_id, patterns=json.dumps(patterns))
        updated += 1

    _log.info("detect_patterns.done", updated=updated)
    return {"updated": updated}
