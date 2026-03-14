from typing import Any

from src.db import supabase as db
from src.llm.registry import get_embedding_provider
from src.tools.registry import register_tool
from src.telemetry.logger import get_logger

_log = get_logger("tools.db")


@register_tool("generate_embedding")
async def generate_embedding(text: str) -> list[float]:
    if not text:
        _log.warning("generate_embedding.empty_text")
        return []
    embedder = get_embedding_provider()
    return await embedder.embed(text)


@register_tool("save_items")
async def save_items(
    user_id: str,
    items: list[dict[str, Any]] | dict[str, Any] | None = None,
    source_message_id: str | None = None,
) -> list[dict[str, Any]]:
    if items is None:
        return []
    if isinstance(items, dict):
        items = items.get("items", [])
    if not isinstance(items, list):
        _log.warning("save_items.invalid_type", type=type(items).__name__)
        return []
    saved = []
    for item in items:
        if not isinstance(item, dict):
            continue
        result = await db.save_item(
            user_id=user_id,
            raw_text=item.get("raw_text", ""),
            interpreted_action=item.get("interpreted_action", ""),
            deadline_type=item.get("deadline_type"),
            deadline_at=item.get("deadline_at"),
            urgency_score=item.get("urgency_score", 0.0),
            energy_estimate=item.get("energy_estimate"),
            source_message_id=source_message_id,
            entity_ids=item.get("entity_ids"),
        )
        await db.save_item_event(
            item_id=str(result["id"]),
            user_id=user_id,
            event_type="created",
        )
        saved.append(result)
    return saved


@register_tool("search_semantic")
async def search_semantic(
    user_id: str,
    embedding: list[float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not embedding:
        return []
    return await db.search_items_semantic(user_id, embedding, limit)


@register_tool("search_hybrid")
async def search_hybrid(
    user_id: str,
    embedding: list[float] | None = None,
    query_text: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not embedding or not query_text:
        return []
    return await db.search_items_hybrid(user_id, embedding, query_text, limit)


@register_tool("search_text")
async def search_text(
    user_id: str,
    query_text: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not query_text:
        return []
    return await db.search_items_text(user_id, query_text, limit)


@register_tool("mark_item_done")
async def mark_item_done(
    item: dict[str, Any] | str | None,
    user_id: str,
) -> dict[str, Any] | None:
    if item is None:
        return None
    if isinstance(item, dict):
        item_id = item.get("id")
        if not item_id:
            _log.warning("mark_item_done.missing_id")
            return None
        item_id = str(item_id)
    else:
        item_id = str(item)
    result = await db.update_item(item_id, user_id, status="done")
    await db.save_item_event(
        item_id=item_id,
        user_id=user_id,
        event_type="done",
    )
    return result
