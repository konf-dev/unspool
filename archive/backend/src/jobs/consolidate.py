"""Async consolidation — dedup, cross-link, and clean up primitives.

Runs daily after evolve_graph. Responsibilities (to implement):

1. DEDUP ITEMS: Find near-duplicate items (same user, similar interpreted_action
   via embedding cosine similarity > 0.95). Merge: keep the one with more metadata,
   mark the other as deprioritized. Update any collection references.

2. LINK ITEMS TO GRAPH: For items that don't have a corresponding graph node,
   check if a node with similar content exists. If so, create an edge linking
   the item's source_message_id to the node. This lets graph retrieval surface
   items by relationship, not just by deadline/urgency.

3. AUTO-CREATE TRACKERS: Scan recent save_items tool calls for patterns that
   look like trackable values (numbers with units, recurring similar items).
   If the user has logged "fuel" 3+ times as items instead of tracker entries,
   auto-create a tracker and offer to convert.

4. PROMOTE TO RECURRING: If the same item title appears 3+ times (created,
   done, re-created), suggest or auto-create a recurring event for it.
   E.g., "do laundry" appearing weekly → recurring event.

5. DISSOLVE STALE COLLECTIONS: Collections not accessed in 30+ days → mark
   as inactive. Items in them remain but are no longer grouped.

6. EXPIRE PROACTIVE MESSAGES: Mark proactive_messages past expires_at as expired.

7. CLEAN NOTIFICATION HISTORY: Delete notification_history entries older than
   90 days to prevent unbounded growth.
"""

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.consolidate")


@observe("job.consolidate")
async def run_consolidate() -> dict:
    pool = db.get_pool()
    stats: dict[str, int] = {}

    # Phase 1: Expire stale proactive messages
    try:
        result = await pool.execute(
            """
            UPDATE proactive_messages SET status = 'expired'
            WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at < now()
            """,
        )
        count = int(result.split()[-1]) if result else 0
        stats["proactive_expired"] = count
    except Exception:
        _log.warning("consolidate.proactive_expire_failed", exc_info=True)

    # Phase 2: Clean old notification history (>90 days)
    try:
        result = await pool.execute(
            "DELETE FROM notification_history WHERE created_at < now() - interval '90 days'",
        )
        count = int(result.split()[-1]) if result else 0
        stats["notif_history_cleaned"] = count
    except Exception:
        _log.warning("consolidate.notif_cleanup_failed", exc_info=True)

    # Phase 3: Dissolve stale collections (>30 days inactive)
    try:
        result = await pool.execute(
            """
            UPDATE collections SET active = false
            WHERE active = true AND updated_at < now() - interval '30 days'
            """,
        )
        count = int(result.split()[-1]) if result else 0
        stats["collections_dissolved"] = count
    except Exception:
        _log.warning("consolidate.collections_dissolve_failed", exc_info=True)

    # TODO: Phases 1-4 from docstring (dedup, linking, auto-trackers, promote recurring)
    # These require LLM calls and more complex logic. Implement when the system
    # has enough real data to test against.

    _log.info("consolidate.done", stats=stats)
    return stats
