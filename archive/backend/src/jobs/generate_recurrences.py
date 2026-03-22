"""Generate next instances of recurring events.

Runs daily. Finds events with rrule that need their next occurrence
generated, and creates them.
"""

from datetime import datetime, timezone
from typing import Any

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.generate_recurrences")


@observe("job.generate_recurrences")
async def run_generate_recurrences() -> dict[str, Any]:
    pool = db.get_pool()

    # Find recurring events where we need to generate the next occurrence
    # An event needs a new occurrence if:
    # 1. It has an rrule
    # 2. It's active
    # 3. Its starts_at is in the past (the current occurrence has passed)
    rows = await pool.fetch(
        """
        SELECT * FROM events
        WHERE rrule IS NOT NULL
          AND status = 'active'
          AND starts_at IS NOT NULL
          AND starts_at < now()
        ORDER BY starts_at ASC
        LIMIT 200
        """,
    )

    generated = 0
    errors = 0

    for event in rows:
        event_id = str(event["id"])
        user_id = str(event["user_id"])
        rrule_str = event.get("rrule", "")

        try:
            next_at = _next_occurrence(rrule_str, event["starts_at"])
            if not next_at:
                continue

            # Calculate duration to preserve end time
            duration = None
            if event.get("ends_at") and event.get("starts_at"):
                duration = event["ends_at"] - event["starts_at"]

            next_end = (next_at + duration) if duration else None

            # Update the event's starts_at/ends_at to the next occurrence
            update_fields: dict[str, Any] = {"starts_at": next_at}
            if next_end:
                update_fields["ends_at"] = next_end

            set_clauses = []
            params: list[Any] = []
            for i, (key, value) in enumerate(update_fields.items(), start=1):
                set_clauses.append(f"{key} = ${i}")
                params.append(value)

            params.append(event_id)
            await pool.execute(
                f"UPDATE events SET {', '.join(set_clauses)} WHERE id = ${len(params)}::uuid",
                *params,
            )

            generated += 1

        except Exception:
            errors += 1
            _log.warning(
                "generate_recurrences.event_failed",
                event_id=event_id,
                user_id=user_id,
                exc_info=True,
            )

    _log.info("generate_recurrences.done", generated=generated, errors=errors)
    return {"generated": generated, "errors": errors}


def _next_occurrence(rrule_str: str, after: datetime) -> datetime | None:
    try:
        from dateutil.rrule import rrulestr

        now = datetime.now(timezone.utc)
        rule = rrulestr(
            f"DTSTART:{after.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}"
        )
        next_dt = rule.after(now)
        return next_dt
    except ImportError:
        _log.warning("generate_recurrences.dateutil_not_available")
        return None
    except Exception:
        _log.warning(
            "generate_recurrences.rrule_parse_failed",
            rrule=rrule_str,
            exc_info=True,
        )
        return None
