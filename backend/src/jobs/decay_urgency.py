from datetime import datetime, timezone

from src.db.supabase import batch_update_items, get_all_open_items_for_decay
from src.telemetry.logger import get_logger

_log = get_logger("jobs.decay_urgency")

_SOFT_DECAY_FACTOR = 0.95
_AUTO_EXPIRE_DAYS = 30
_AUTO_EXPIRE_THRESHOLD = 0.1


async def run_decay_urgency() -> dict:
    items = await get_all_open_items_for_decay()
    _log.info("decay_urgency.start", item_count=len(items))

    now = datetime.now(timezone.utc)
    updates: list[dict] = []
    expired = 0

    for item in items:
        item_id = str(item["id"])
        urgency = float(item.get("urgency_score", 0.0))
        deadline_type = item.get("deadline_type")
        deadline_at = item.get("deadline_at")
        created_at = item.get("created_at")

        if deadline_type == "hard" and deadline_at:
            hours_until = (deadline_at - now).total_seconds() / 3600
            if hours_until <= 0:
                new_urgency = 1.0
            elif hours_until <= 24:
                new_urgency = min(1.0, 0.7 + (24 - hours_until) / 80)
            elif hours_until <= 72:
                new_urgency = max(urgency, 0.5 + (72 - hours_until) / 96)
            else:
                new_urgency = urgency
            if abs(new_urgency - urgency) > 0.01:
                updates.append({"id": item_id, "urgency_score": new_urgency})

        elif deadline_type == "soft" and deadline_at:
            if deadline_at < now:
                new_urgency = urgency * _SOFT_DECAY_FACTOR
                updates.append({"id": item_id, "urgency_score": new_urgency})

        else:
            if created_at:
                age_days = (now - created_at).days
                if age_days > _AUTO_EXPIRE_DAYS and urgency < _AUTO_EXPIRE_THRESHOLD:
                    updates.append({"id": item_id, "status": "expired"})
                    expired += 1

    if updates:
        await batch_update_items(updates)

    _log.info("decay_urgency.done", updated=len(updates), expired=expired)
    return {"updated": len(updates), "expired": expired}
