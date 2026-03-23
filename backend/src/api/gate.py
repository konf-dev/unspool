"""Rate limiting gate — tier-aware daily message limits."""

from fastapi import HTTPException

from src.auth.supabase_auth import EVAL_USER_ID
from src.core.config_loader import load_config
from src.db import redis
from src.db.queries import get_user_tier
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

_log = get_logger("api.gate")


async def check_gate(user_id: str) -> None:
    """Check rate limit for user. Raises 429 if exceeded."""
    if user_id == EVAL_USER_ID:
        return

    gate_config = load_config("gate")
    rate_limits = gate_config.get("rate_limits", {})

    tier = "free"
    try:
        cached_tier = await redis.session_get(user_id, "tier")
        if cached_tier:
            tier = cached_tier
        else:
            tier = await get_user_tier(user_id)
            await redis.session_set(user_id, "tier", tier)
    except Exception as e:
        report_error("gate.tier_check_failed", e, user_id=user_id)

    tier_config = rate_limits.get(tier, rate_limits.get("free", {}))
    daily_limit = tier_config.get("daily_messages", 10)

    if daily_limit < 0:
        return

    try:
        allowed, remaining = await redis.rate_limit_check(user_id, daily_limit)
    except Exception as e:
        report_error("gate.rate_limit_check_failed", e, user_id=user_id)
        return  # fail open

    if not allowed:
        message = tier_config.get("message", "You've reached your daily message limit.")
        raise HTTPException(status_code=429, detail=message)
