"""Expire OPEN nodes past their deadlines."""

import json
from datetime import datetime, timezone

from sqlalchemy import text

from src.core.database import AsyncSessionLocal
from src.telemetry.logger import get_logger

_log = get_logger("jobs.expire_items")


async def run_expire_items() -> dict:
    async with AsyncSessionLocal() as session:
        # Find OPEN action nodes with hard deadlines that have passed
        expired_rows = await session.execute(text("""
            SELECT va.node_id, va.user_id, va.content
            FROM vw_actionable va
            WHERE va.deadline IS NOT NULL
              AND va.deadline::timestamptz < NOW()
              AND va.deadline_type = 'hard'
            LIMIT 100
        """))
        rows = expired_rows.mappings().all()

        if rows:
            node_ids = [str(r["node_id"]) for r in rows]

            # Archive the nodes — use IN subselect matching the same view query
            # to avoid array parameter issues with SQLAlchemy text()
            await session.execute(text("""
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

            # Record events for each archived node
            now = datetime.now(timezone.utc)
            for r in rows:
                await session.execute(text("""
                    INSERT INTO event_stream (user_id, event_type, payload, created_at)
                    VALUES (CAST(:uid AS uuid), 'NodeArchived', CAST(:payload AS jsonb), :ts)
                """), {
                    "uid": str(r["user_id"]),
                    "payload": json.dumps({"node_id": str(r["node_id"]), "content": r["content"], "reason": "hard_deadline_expired"}),
                    "ts": now,
                })

        expired_hard = len(rows)
        await session.commit()

    _log.info("expire_items.done", expired_hard=expired_hard)
    return {"expired_hard": expired_hard}
