"""Expire OPEN nodes past their deadlines."""

from sqlalchemy import text

from src.core.database import AsyncSessionLocal
from src.telemetry.logger import get_logger

_log = get_logger("jobs.expire_items")


async def run_expire_items() -> dict:
    async with AsyncSessionLocal() as session:
        # Archive OPEN action nodes with hard deadlines that have passed
        result = await session.execute(text("""
            UPDATE graph_nodes SET node_type = 'archived_action'
            WHERE id IN (
                SELECT va.node_id FROM vw_actionable va
                WHERE va.deadline IS NOT NULL
                  AND va.deadline::timestamptz < NOW()
                  AND va.deadline_type = 'hard'
                LIMIT 100
            )
            AND node_type = 'action'
        """))
        expired_hard = result.rowcount

        await session.commit()

    _log.info("expire_items.done", expired_hard=expired_hard)
    return {"expired_hard": expired_hard}
