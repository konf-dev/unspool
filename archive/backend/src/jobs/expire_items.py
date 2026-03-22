"""Simplified item expiration — replaces decay_urgency.

Expires items past their hard deadline and auto-expires stale low-urgency items.
Uses paginated queries instead of loading all items into memory.
"""

from datetime import datetime, timezone

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.expire_items")

BATCH_SIZE = 100
STALE_AGE_DAYS = 30
STALE_URGENCY_THRESHOLD = 0.1


@observe("job.expire_items")
async def run_expire_items() -> dict:
    pool = db.get_pool()
    now = datetime.now(timezone.utc)
    expired_hard = 0
    expired_stale = 0

    # Phase 1: Expire items past their hard deadline
    while True:
        result = await pool.execute(
            """
            UPDATE items SET status = 'expired'
            WHERE id IN (
                SELECT id FROM items
                WHERE status = 'open'
                  AND deadline_type = 'hard'
                  AND deadline_at IS NOT NULL
                  AND deadline_at < $1
                LIMIT $2
            )
            """,
            now,
            BATCH_SIZE,
        )
        count = int(result.split()[-1]) if result else 0
        expired_hard += count
        if count < BATCH_SIZE:
            break

    # Phase 2: Expire stale low-urgency items with no deadline
    while True:
        result = await pool.execute(
            """
            UPDATE items SET status = 'expired'
            WHERE id IN (
                SELECT id FROM items
                WHERE status = 'open'
                  AND deadline_type = 'none'
                  AND urgency_score < $1
                  AND created_at < $2 - ($3 || ' days')::interval
                LIMIT $4
            )
            """,
            STALE_URGENCY_THRESHOLD,
            now,
            str(STALE_AGE_DAYS),
            BATCH_SIZE,
        )
        count = int(result.split()[-1]) if result else 0
        expired_stale += count
        if count < BATCH_SIZE:
            break

    total = expired_hard + expired_stale
    _log.info(
        "expire_items.done",
        expired_hard=expired_hard,
        expired_stale=expired_stale,
        total=total,
    )
    return {
        "expired_hard": expired_hard,
        "expired_stale": expired_stale,
        "total": total,
    }
