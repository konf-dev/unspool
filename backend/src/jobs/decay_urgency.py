from datetime import datetime, timezone

from src.db.supabase import batch_update_items, get_all_open_items_for_decay
from src.orchestrator.config_loader import load_config
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.decay_urgency")


@observe("job.decay_urgency")
async def run_decay_urgency() -> dict:
    try:
        config = load_config("scoring")
    except FileNotFoundError:
        config = {}

    decay_config = config.get("decay", {})
    soft_decay_factor = decay_config.get("soft_decay_factor", 0.95)
    auto_expire_days = decay_config.get("auto_expire_days", 30)
    auto_expire_threshold = decay_config.get("auto_expire_threshold", 0.1)

    hard_ramp = decay_config.get("hard_ramp", {})
    ramp_overdue = hard_ramp.get("overdue", 1.0)
    ramp_24h_base = hard_ramp.get("within_24h_base", 0.7)
    ramp_24h_divisor = hard_ramp.get("within_24h_divisor", 80)
    ramp_72h_base = hard_ramp.get("within_72h_base", 0.5)
    ramp_72h_divisor = hard_ramp.get("within_72h_divisor", 96)

    items = await get_all_open_items_for_decay()
    _log.info("decay_urgency.start", item_count=len(items))

    now = datetime.now(timezone.utc)
    updates: list[dict] = []
    expired = 0

    for item in items:
        item_id = str(item["id"])
        item_user_id = str(item["user_id"])
        urgency = float(item.get("urgency_score", 0.0))
        deadline_type = item.get("deadline_type")
        deadline_at = item.get("deadline_at")
        created_at = item.get("created_at")

        if deadline_type == "hard" and deadline_at:
            hours_until = (deadline_at - now).total_seconds() / 3600
            if hours_until <= 0:
                new_urgency = ramp_overdue
            elif hours_until <= 24:
                new_urgency = min(
                    1.0, ramp_24h_base + (24 - hours_until) / ramp_24h_divisor
                )
            elif hours_until <= 72:
                new_urgency = max(
                    urgency, ramp_72h_base + (72 - hours_until) / ramp_72h_divisor
                )
            else:
                new_urgency = urgency
            if abs(new_urgency - urgency) > 0.01:
                updates.append(
                    {
                        "id": item_id,
                        "user_id": item_user_id,
                        "urgency_score": new_urgency,
                    }
                )

        elif deadline_type == "soft" and deadline_at:
            if deadline_at < now:
                new_urgency = urgency * soft_decay_factor
                updates.append(
                    {
                        "id": item_id,
                        "user_id": item_user_id,
                        "urgency_score": new_urgency,
                    }
                )

        else:
            if created_at:
                age_days = (now - created_at).days
                if age_days > auto_expire_days and urgency < auto_expire_threshold:
                    updates.append(
                        {"id": item_id, "user_id": item_user_id, "status": "expired"}
                    )
                    expired += 1

    if updates:
        await batch_update_items(updates)

    _log.info("decay_urgency.done", updated=len(updates), expired=expired)
    return {"updated": len(updates), "expired": expired}
