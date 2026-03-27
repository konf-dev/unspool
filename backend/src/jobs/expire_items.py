"""Expire OPEN nodes past their deadlines — tiered by deadline_type."""

import json
from datetime import datetime, timezone

from sqlalchemy import text

from src.core.database import AsyncSessionLocal
from src.telemetry.logger import get_logger

_log = get_logger("jobs.expire_items")


async def run_expire_items() -> dict:
    results: dict[str, int] = {}
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # 1. Hard deadlines: archive at T+0 (immediate)
        results["expired_hard"] = await _expire_by_type(
            session, deadline_type="hard", condition="va.deadline::timestamptz < NOW()", now=now,
        )

        # 2. Soft deadlines: archive at T+48h
        results["expired_soft"] = await _expire_by_type(
            session, deadline_type="soft",
            condition="va.deadline::timestamptz < NOW() - interval '48 hours'", now=now,
        )

        # 3. Routine deadlines: archive at midnight of deadline day
        results["expired_routine"] = await _expire_by_type(
            session, deadline_type="routine",
            condition="va.deadline::date < CURRENT_DATE", now=now,
        )

        # 4. Undated items: archive after 14 days of no edge updates
        stale_rows = await session.execute(text("""
            SELECT va.node_id, va.user_id, va.content
            FROM vw_actionable va
            WHERE va.deadline IS NULL
              AND va.created_at < NOW() - interval '14 days'
              AND NOT EXISTS (
                  SELECT 1 FROM graph_edges ge
                  WHERE ge.source_node_id = va.node_id
                    AND ge.updated_at > NOW() - interval '14 days'
              )
            LIMIT 100
        """))
        stale = stale_rows.mappings().all()

        if stale:
            await session.execute(text("""
                UPDATE graph_nodes SET node_type = 'archived_action'
                WHERE id IN (
                    SELECT va.node_id FROM vw_actionable va
                    WHERE va.deadline IS NULL
                      AND va.created_at < NOW() - interval '14 days'
                      AND NOT EXISTS (
                          SELECT 1 FROM graph_edges ge
                          WHERE ge.source_node_id = va.node_id
                            AND ge.updated_at > NOW() - interval '14 days'
                      )
                    LIMIT 100
                )
                AND node_type IN ('action', 'memory', 'concept')
            """))

            for r in stale:
                await session.execute(text("""
                    INSERT INTO event_stream (user_id, event_type, payload, created_at)
                    VALUES (CAST(:uid AS uuid), 'NodeArchived', CAST(:payload AS jsonb), :ts)
                """), {
                    "uid": str(r["user_id"]),
                    "payload": json.dumps({"node_id": str(r["node_id"]), "content": r["content"], "reason": "stale_undated_14d"}),
                    "ts": now,
                })

        results["expired_stale"] = len(stale)
        await session.commit()

    _log.info("expire_items.done", **results)
    return results


async def _expire_by_type(session, deadline_type: str, condition: str, now: datetime) -> int:
    """Archive nodes of a specific deadline_type matching the given SQL condition."""
    # Find matching items
    query = f"""
        SELECT va.node_id, va.user_id, va.content
        FROM vw_actionable va
        WHERE va.deadline IS NOT NULL
          AND {condition}
          AND va.deadline_type = :dtype
        LIMIT 100
    """
    expired_rows = await session.execute(text(query), {"dtype": deadline_type})
    rows = expired_rows.mappings().all()

    if rows:
        # Archive the nodes
        archive_query = f"""
            UPDATE graph_nodes SET node_type = 'archived_action'
            WHERE id IN (
                SELECT va.node_id FROM vw_actionable va
                WHERE va.deadline IS NOT NULL
                  AND {condition}
                  AND va.deadline_type = :dtype
                LIMIT 100
            )
            AND node_type IN ('action', 'memory', 'concept')
        """
        await session.execute(text(archive_query), {"dtype": deadline_type})

        # Record events
        for r in rows:
            await session.execute(text("""
                INSERT INTO event_stream (user_id, event_type, payload, created_at)
                VALUES (CAST(:uid AS uuid), 'NodeArchived', CAST(:payload AS jsonb), :ts)
            """), {
                "uid": str(r["user_id"]),
                "payload": json.dumps({
                    "node_id": str(r["node_id"]),
                    "content": r["content"],
                    "reason": f"{deadline_type}_deadline_expired",
                }),
                "ts": now,
            })

    return len(rows)
