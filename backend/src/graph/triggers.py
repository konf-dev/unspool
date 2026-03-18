"""Retrieval triggers — SQL-first, using neighbor cache."""

from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone

from src.graph import db
from src.graph.types import TriggerResult
from src.telemetry.logger import get_logger

_log = get_logger("graph.triggers")

TriggerFn = Callable[..., Coroutine[None, None, TriggerResult]]
_trigger_registry: dict[str, TriggerFn] = {}


def register_trigger(name: str):
    def decorator(fn: TriggerFn) -> TriggerFn:
        _trigger_registry[name] = fn
        return fn

    return decorator


def get_trigger(name: str) -> TriggerFn | None:
    return _trigger_registry.get(name)


@register_trigger("vector_search")
async def trigger_semantic(user_id: str, context: dict, params: dict) -> TriggerResult:
    embedding = context.get("message_embedding")
    if not embedding:
        return TriggerResult(trigger_name="semantic")

    limit = params.get("limit", 15)
    min_sim = params.get("min_similarity", 0.3)
    nodes = await db.search_nodes_semantic(user_id, embedding, limit, min_sim)
    return TriggerResult(
        trigger_name="semantic",
        node_ids=[str(n["id"]) for n in nodes],
        metadata={"count": len(nodes)},
    )


@register_trigger("date_proximity")
async def trigger_temporal(user_id: str, context: dict, params: dict) -> TriggerResult:
    nodes = await db.find_temporal_nodes(user_id)
    node_ids = [str(n["id"]) for n in nodes]
    return TriggerResult(
        trigger_name="temporal",
        node_ids=node_ids,
        metadata={"count": len(node_ids)},
    )


@register_trigger("status_query")
async def trigger_status(user_id: str, context: dict, params: dict) -> TriggerResult:
    status = params.get("status", "not done")
    direction = params.get("direction", "incoming")
    time_window = params.get("time_window_hours")

    nodes = await db.find_nodes_by_status_neighbor(user_id, status, direction)

    if time_window:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=time_window)
        nodes = [
            n for n in nodes if n.get("last_activated_at", "") > cutoff.isoformat()
        ]

    node_ids = [str(n["id"]) for n in nodes]
    return TriggerResult(
        trigger_name=f"status_{status.replace(' ', '_')}",
        node_ids=node_ids,
        metadata={"status": status, "count": len(node_ids)},
    )


@register_trigger("recency")
async def trigger_recent(user_id: str, context: dict, params: dict) -> TriggerResult:
    hours = params.get("hours", 24)
    limit = params.get("limit", 10)

    nodes = await db.get_recent_nodes(user_id, limit=limit)

    if hours < 8760:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        nodes = [
            n for n in nodes if n.get("last_activated_at", "") > cutoff.isoformat()
        ]

    node_ids = [str(n["id"]) for n in nodes]
    return TriggerResult(
        trigger_name="recent",
        node_ids=node_ids,
        metadata={"count": len(node_ids)},
    )


@register_trigger("walk")
async def trigger_walk(user_id: str, context: dict, params: dict) -> TriggerResult:
    start_ids = list(context.get("collected_node_ids", set()))
    max_nodes = params.get("max_nodes", 30)

    if not start_ids:
        return TriggerResult(trigger_name="walk")

    existing = context.get("collected_node_ids", set())
    neighbors = await db.get_neighbors(
        start_ids, exclude_ids=list(existing), limit=max_nodes
    )
    node_ids = [str(n["neighbor_id"]) for n in neighbors]

    return TriggerResult(
        trigger_name="walk",
        node_ids=node_ids,
        metadata={"walked_from": len(start_ids), "found": len(node_ids)},
    )
