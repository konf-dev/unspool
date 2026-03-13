import random
from typing import Any

from src.db.redis import cache_get, cache_set
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.variants")

_STICKY_TTL = 86400 * 30  # 30 days


async def select_variant(
    user_id: str,
    experiment: str,
    variants_config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    sticky_key = f"variant:{user_id}:{experiment}"
    existing = await cache_get(sticky_key)
    if existing and existing in variants_config:
        _log.info("variant.sticky_hit", experiment=experiment, variant=existing)
        return existing, variants_config[existing].get("overrides", {})

    variants = list(variants_config.keys())
    weights = [variants_config[v].get("weight", 1.0) for v in variants]

    chosen = random.choices(variants, weights=weights, k=1)[0]

    await cache_set(sticky_key, chosen, _STICKY_TTL)
    _log.info("variant.assigned", experiment=experiment, variant=chosen)
    return chosen, variants_config[chosen].get("overrides", {})
