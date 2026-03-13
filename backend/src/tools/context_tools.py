from typing import Any

from src.db import supabase as db
from src.tools.registry import register_tool


@register_tool("fetch_messages")
async def fetch_messages(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return await db.get_messages(user_id, limit=limit)


@register_tool("fetch_profile")
async def fetch_profile(user_id: str) -> dict[str, Any]:
    return await db.get_profile(user_id)


@register_tool("fetch_items")
async def fetch_items(user_id: str) -> list[dict[str, Any]]:
    return await db.get_open_items(user_id)


@register_tool("fetch_urgent_items")
async def fetch_urgent_items(user_id: str, hours: int = 48) -> list[dict[str, Any]]:
    return await db.get_urgent_items(user_id, hours=hours)


@register_tool("fetch_memories")
async def fetch_memories(
    user_id: str,
    embedding: list[float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if embedding:
        return await db.search_memories_semantic(user_id, embedding, limit=limit)
    # Without an embedding, fetch recent memories by timestamp
    pool = db.get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memories WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


@register_tool("fetch_entities")
async def fetch_entities(user_id: str) -> list[dict[str, Any]]:
    pool = db.get_pool()
    rows = await pool.fetch(
        "SELECT * FROM entities WHERE user_id = $1 "
        "ORDER BY last_mentioned_at DESC NULLS LAST",
        user_id,
    )
    return [dict(r) for r in rows]


@register_tool("fetch_calendar_events")
async def fetch_calendar_events(user_id: str) -> list[dict[str, Any]]:
    pool = db.get_pool()
    rows = await pool.fetch(
        "SELECT * FROM calendar_events WHERE user_id = $1 "
        "AND start_at >= now() ORDER BY start_at ASC LIMIT 20",
        user_id,
    )
    return [dict(r) for r in rows]
