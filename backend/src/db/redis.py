from datetime import datetime, timezone

from upstash_redis.asyncio import Redis

from src.config import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("db.redis")
_redis: Redis | None = None

_TTL_WORKING = 300  # 5 minutes
_TTL_SHORT_TERM = 3600  # 1 hour


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis(
            url=settings.UPSTASH_REDIS_REST_URL,
            token=settings.UPSTASH_REDIS_REST_TOKEN,
        )
    return _redis


def _decode_result(result: object) -> str | None:
    if result is None:
        return None
    if isinstance(result, bytes):
        return result.decode("utf-8")
    return str(result)


async def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    r = get_redis()
    await r.set(key, value, ex=ttl_seconds)


async def cache_get(key: str) -> str | None:
    r = get_redis()
    result = await r.get(key)
    return _decode_result(result)


async def cache_delete(key: str) -> None:
    r = get_redis()
    await r.delete(key)


async def rate_limit_check(user_id: str, daily_limit: int) -> tuple[bool, int]:
    r = get_redis()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"rate:{user_id}:{today}"

    # Pipeline: bundle SET NX + INCR into one HTTP roundtrip
    pipe = r.pipeline()
    pipe.set(key, 0, ex=86400, nx=True)
    pipe.incr(key)
    results = await pipe.exec()

    count = int(results[1])  # type: ignore[arg-type]  # upstash pipeline returns list[RESTResultT]
    allowed = count <= daily_limit
    remaining = max(0, daily_limit - count)
    return allowed, remaining


async def rate_limit_increment(user_id: str) -> None:
    # No-op: incrementing happens atomically inside rate_limit_check
    pass


async def session_set(user_id: str, key: str, value: str) -> None:
    r = get_redis()
    await r.set(f"session:{user_id}:{key}", value, ex=_TTL_SHORT_TERM)


async def session_get(user_id: str, key: str) -> str | None:
    r = get_redis()
    result = await r.get(f"session:{user_id}:{key}")
    return _decode_result(result)


async def context_set(user_id: str, key: str, value: str) -> None:
    r = get_redis()
    await r.set(f"context:{user_id}:{key}", value, ex=_TTL_WORKING)


async def context_get(user_id: str, key: str) -> str | None:
    r = get_redis()
    result = await r.get(f"context:{user_id}:{key}")
    return _decode_result(result)
