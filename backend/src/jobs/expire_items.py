"""Expire OPEN nodes past their deadlines — tiered by deadline_type."""

import json
from datetime import datetime, timezone

from sqlalchemy import text

from src.core.config_loader import hp
from src.core.database import AsyncSessionLocal
from src.telemetry.logger import get_logger

_log = get_logger("jobs.expire_items")

# Fixed SQL queries per deadline type. No string interpolation — each condition
# is a complete, static query with only bind parameters.
_HARD_DEADLINE_SELECT = text("""
    SELECT va.node_id, va.user_id, va.content
    FROM vw_actionable va
    WHERE va.deadline IS NOT NULL
      AND va.deadline::timestamptz < NOW()
      AND va.deadline_type = 'hard'
    LIMIT :lim
""")

_SOFT_DEADLINE_SELECT = text("""
    SELECT va.node_id, va.user_id, va.content
    FROM vw_actionable va
    WHERE va.deadline IS NOT NULL
      AND va.deadline::timestamptz < NOW() - make_interval(hours => :grace_hours)
      AND va.deadline_type = 'soft'
    LIMIT :lim
""")

_ROUTINE_DEADLINE_SELECT = text("""
    SELECT va.node_id, va.user_id, va.content
    FROM vw_actionable va
    WHERE va.deadline IS NOT NULL
      AND va.deadline::date < CURRENT_DATE
      AND va.deadline_type = 'routine'
    LIMIT :lim
""")

_STALE_UNDATED_SELECT = text("""
    SELECT va.node_id, va.user_id, va.content
    FROM vw_actionable va
    WHERE va.deadline IS NULL
      AND va.created_at < NOW() - :stale_interval::interval
      AND NOT EXISTS (
          SELECT 1 FROM graph_edges ge
          WHERE ge.source_node_id = va.node_id
            AND ge.updated_at > NOW() - :stale_interval::interval
      )
    LIMIT :lim
""")

_ARCHIVE_BY_IDS = text("""
    UPDATE graph_nodes SET node_type = 'archived_action'
    WHERE id = ANY(:ids)
      AND node_type IN ('action', 'memory', 'concept')
""")

_RECORD_EVENT = text("""
    INSERT INTO event_stream (user_id, event_type, payload, created_at)
    VALUES (CAST(:uid AS uuid), 'NodeArchived', CAST(:payload AS jsonb), :ts)
""")


async def run_expire_items() -> dict:
    results: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    grace_hours = int(hp("expiration", "soft_deadline_grace_hours", 48))
    stale_days = int(hp("expiration", "undated_stale_days", 14))
    batch_limit = int(hp("expiration", "batch_limit", 100))

    async with AsyncSessionLocal() as session:
        # 1. Hard deadlines: archive immediately when past
        results["expired_hard"] = await _archive_matching(
            session, _HARD_DEADLINE_SELECT, {"lim": batch_limit},
            reason="hard_deadline_expired", now=now,
        )

        # 2. Soft deadlines: archive after grace period
        results["expired_soft"] = await _archive_matching(
            session, _SOFT_DEADLINE_SELECT,
            {"grace_hours": grace_hours, "lim": batch_limit},
            reason="soft_deadline_expired", now=now,
        )

        # 3. Routine deadlines: archive at midnight of deadline day
        results["expired_routine"] = await _archive_matching(
            session, _ROUTINE_DEADLINE_SELECT, {"lim": batch_limit},
            reason="routine_deadline_expired", now=now,
        )

        # 4. Undated items: archive after N days of no edge updates
        stale_interval = f"{stale_days} days"
        results["expired_stale"] = await _archive_matching(
            session, _STALE_UNDATED_SELECT,
            {"stale_interval": stale_interval, "lim": batch_limit},
            reason="stale_undated", now=now,
        )

        await session.commit()

    _log.info("expire_items.done", **results)
    return results


async def _archive_matching(
    session, select_query, params: dict,
    reason: str, now: datetime,
) -> int:
    """Run a SELECT to find expiring nodes, archive them, and record events."""
    rows = (await session.execute(select_query, params)).mappings().all()
    if not rows:
        return 0

    row_ids = [r["node_id"] for r in rows]
    await session.execute(_ARCHIVE_BY_IDS, {"ids": row_ids})

    for r in rows:
        await session.execute(_RECORD_EVENT, {
            "uid": str(r["user_id"]),
            "payload": json.dumps({
                "node_id": str(r["node_id"]),
                "content": r["content"],
                "reason": reason,
            }),
            "ts": now,
        })

    return len(rows)
