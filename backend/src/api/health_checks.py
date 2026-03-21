import asyncio
import time
from typing import Any

import httpx

from src.config import get_settings
from src.db.supabase import get_pool


async def _check_db() -> dict[str, Any]:
    pool = get_pool()
    await pool.fetchval("SELECT 1")
    return {"status": "ok"}


async def _check_redis() -> dict[str, Any]:
    from src.db.redis import get_redis

    r = get_redis()
    await r.ping()
    return {"status": "ok"}


async def _check_qstash() -> dict[str, Any]:
    from src.integrations.qstash import _get_client

    client = _get_client()
    await client.schedule.list()
    return {"status": "ok"}


async def _check_llm() -> dict[str, Any]:
    from src.llm.registry import get_llm_provider

    provider = get_llm_provider()
    await provider.generate(
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )
    return {"status": "ok"}


async def _check_langfuse() -> dict[str, Any]:
    settings = get_settings()
    if not settings.LANGFUSE_HOST:
        return {"status": "skipped", "reason": "not configured"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{settings.LANGFUSE_HOST}/api/public/health")
        resp.raise_for_status()
    return {"status": "ok"}


async def _run_check(
    name: str,
    coro: Any,
    timeout: float = 5.0,
) -> tuple[str, dict[str, Any]]:
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000)
        return name, result
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return name, {
            "status": "error",
            "error": str(exc),
            "latency_ms": latency_ms,
        }


async def run_all_checks() -> dict[str, dict[str, Any]]:
    checks = [
        _run_check("db", _check_db()),
        _run_check("redis", _check_redis()),
        _run_check("qstash", _check_qstash()),
        _run_check("llm", _check_llm()),
        _run_check("langfuse", _check_langfuse()),
    ]
    results = await asyncio.gather(*checks)
    return dict(results)
