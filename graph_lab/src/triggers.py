"""Retrieval triggers — each trigger finds relevant nodes for a given context."""

import re
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone

import structlog
from graph_lab.src import db
from graph_lab.src.types import TriggerResult

logger = structlog.get_logger()

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
        node_ids=[n["id"] for n in nodes],
        metadata={"count": len(nodes)},
    )


@register_trigger("date_proximity")
async def trigger_temporal(user_id: str, context: dict, params: dict) -> TriggerResult:
    """Find nodes with ISO date content near the current time."""
    window_hours = params.get("window_hours", 48)
    include_overdue = params.get("include_overdue", True)

    now = datetime.now(timezone.utc)
    all_nodes = await db.get_all_nodes(user_id)

    iso_date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    matched_ids: list[str] = []

    for node in all_nodes:
        content = node.get("content", "")
        if not iso_date_pattern.match(content):
            continue
        try:
            node_date = datetime.strptime(content, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        # Within future window
        if now <= node_date <= now + timedelta(hours=window_hours):
            matched_ids.append(node["id"])
        # Overdue (past but not too far)
        elif include_overdue and now - timedelta(days=7) <= node_date < now:
            matched_ids.append(node["id"])

    # Also find nodes connected to these date nodes
    connected_ids: list[str] = []
    for nid in matched_ids:
        connected = await db.traverse_from(nid, hops=1, direction="incoming")
        connected_ids.extend(n["id"] for n in connected)

    all_ids = list(set(matched_ids + connected_ids))
    return TriggerResult(
        trigger_name="temporal",
        node_ids=all_ids,
        metadata={"date_nodes": len(matched_ids), "connected": len(connected_ids)},
    )


@register_trigger("status_query")
async def trigger_status(user_id: str, context: dict, params: dict) -> TriggerResult:
    """Find nodes connected to a status node (e.g., 'not done', 'surfaced')."""
    status = params.get("status", "not done")
    direction = params.get("direction", "incoming")
    time_window = params.get("time_window_hours")

    nodes = await db.find_nodes_connected_to(user_id, status, direction)

    # Filter by time window if specified
    if time_window:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=time_window)
        nodes = [n for n in nodes if n.get("last_activated_at", "") > cutoff.isoformat()]

    # Filter out nodes with strength 0 edges to the status
    status_node = await db.find_node_by_content(user_id, status)
    if status_node:
        filtered: list[str] = []
        for n in nodes:
            if direction == "incoming":
                edges = await db.get_edges_from(n["id"])
                relevant = [e for e in edges if e.get("out") == status_node["id"]]
            else:
                edges = await db.get_edges_to(n["id"])
                relevant = [e for e in edges if e.get("in") == status_node["id"]]
            if relevant and all(e.get("strength", 1) > 0.01 for e in relevant):
                filtered.append(n["id"])
        node_ids = filtered
    else:
        node_ids = [n["id"] for n in nodes]

    return TriggerResult(
        trigger_name=f"status_{status.replace(' ', '_')}",
        node_ids=node_ids,
        metadata={"status": status, "count": len(node_ids)},
    )


@register_trigger("recency")
async def trigger_recent(user_id: str, context: dict, params: dict) -> TriggerResult:
    hours = params.get("hours", 24)
    limit = params.get("limit", 10)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    recent = await db.get_recent_nodes(user_id, limit=limit)
    nodes = [n for n in recent if n.get("last_activated_at", "") > cutoff.isoformat()]

    return TriggerResult(
        trigger_name="recent",
        node_ids=[n["id"] for n in nodes],
        metadata={"count": len(nodes)},
    )


@register_trigger("walk")
async def trigger_walk(user_id: str, context: dict, params: dict) -> TriggerResult:
    """Walk N hops from nodes found by previous triggers."""
    start_ids = list(context.get("collected_node_ids", set()))
    hops = params.get("hops", 1)
    max_nodes = params.get("max_nodes", 30)

    if not start_ids:
        return TriggerResult(trigger_name="walk")

    walked = await db.traverse_from_many(user_id, start_ids, hops)

    # Cap and exclude already-collected nodes
    existing = context.get("collected_node_ids", set())
    new_nodes = [n for n in walked if n.get("id") not in existing]
    if len(new_nodes) > max_nodes:
        new_nodes = new_nodes[:max_nodes]

    return TriggerResult(
        trigger_name="walk",
        node_ids=[n["id"] for n in new_nodes],
        metadata={"walked_from": len(start_ids), "found": len(new_nodes)},
    )
