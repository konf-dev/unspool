"""Hot path tools — query_graph, mutate_graph, schedule_reminder.

user_id is NOT a tool parameter — it's injected from LangGraph state in call_tools.
"""

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone as tz
from typing import Any

from sqlalchemy import select, func

from src.core.database import AsyncSessionLocal
from src.core.graph import (
    get_node_neighborhood,
    search_nodes_semantic,
    search_nodes_by_edge_structure,
    upsert_edge,
    update_status_event,
    update_content_event,
    archive_node_event,
    remove_edge_event,
)
from src.core.models import GraphNode, GraphEdge
from src.core.config_loader import hp
from src.integrations.gemini import get_embedding
from src.telemetry.logger import get_logger

from langchain_core.tools import tool

logger = get_logger("hot_path.tools")


def _sanitize_error(e: Exception) -> str:
    """Turn a Python exception into an LLM-readable error string."""
    msg = str(e)
    if isinstance(e, ValueError) and "UUID" in msg:
        return "Error: invalid node ID format. Use a valid UUID from query_graph results."
    if isinstance(e, ValueError):
        return f"Error: invalid argument — {msg}"
    if "connection" in msg.lower() or "timeout" in msg.lower():
        return "Error: database temporarily unavailable. Try again."
    return f"Error: {msg}"


@tool
async def query_graph(
    semantic_query: str | None = None,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Searches the user's memory graph.

    Args:
        semantic_query: Optional search term. If omitted, returns all matching nodes.
        edge_type_filter: Filter by edge type (e.g. 'HAS_DEADLINE', 'IS_STATUS').
        node_type: Filter by node type (e.g. 'action', 'concept', 'person', 'memory').
        date_from: Optional ISO8601 date. Filter results to items with edge dates >= this.
        date_to: Optional ISO8601 date. Filter results to items with edge dates <= this.
        depth: Number of hops to traverse from matched nodes (default 0 = flat search).
               Use 1-2 for context questions like "what's related to X?" or "tell me about project Y".

    At least one of semantic_query, edge_type_filter, or node_type must be provided.
    """
    # user_id will be injected by call_tools — this is a placeholder
    raise RuntimeError("query_graph must be called via call_tools with user_id injection")


@tool
async def mutate_graph(
    action: str,
    node_id: str,
    value: str | None = None,
    target_node_id: str | None = None,
    edge_type: str | None = None,
) -> str:
    """Modifies the user's memory graph. You MUST know the exact node_id first by using query_graph.

    Args:
        action: One of: SET_STATUS, ADD_EDGE, REMOVE_EDGE, UPDATE_CONTENT, ARCHIVE.
        node_id: The UUID of the node to modify.
        value: For SET_STATUS: 'OPEN' or 'DONE'. For UPDATE_CONTENT: the new text.
        target_node_id: For ADD_EDGE/REMOVE_EDGE: the target node UUID.
        edge_type: For ADD_EDGE/REMOVE_EDGE: the edge type (e.g. 'RELATES_TO', 'HAS_DEADLINE').
    """
    # user_id will be injected by call_tools — this is a placeholder
    raise RuntimeError("mutate_graph must be called via call_tools with user_id injection")


@tool
async def schedule_reminder(
    reminder_text: str,
    remind_at: str,
) -> str:
    """Schedule a reminder for the user at a specific time.

    Args:
        reminder_text: What to remind the user about.
        remind_at: ISO8601 timestamp for when to send the reminder (e.g. "2026-03-27T17:00:00Z").
    """
    # user_id will be injected by call_tools — this is a placeholder
    raise RuntimeError("schedule_reminder must be called via call_tools with user_id injection")


@tool
async def get_metrics(
    metric_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]] | str:
    """Get aggregated metric data (totals, counts, averages). Use this instead of
    query_graph for questions like "how much did I spend?" or "how many km did I run?"

    Args:
        metric_name: Optional filter for a specific metric (e.g. "spending", "running").
                     Omit to get summaries of all tracked metrics.
        date_from: Optional ISO8601 date. Only include entries on or after this date.
        date_to: Optional ISO8601 date. Only include entries on or before this date.

    Returns a list of metric summaries, each with: metric name, entry count, total,
    min, max, average, latest value, unit, and date range.
    """
    raise RuntimeError("get_metrics must be called via call_tools with user_id injection")


# Actual implementations called by call_tools with user_id injected

async def _exec_query_graph(
    user_id: str,
    semantic_query: str | None = None,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    depth: int = 0,
) -> list[dict[str, Any]] | str:
    """Returns list of node dicts on success, or an error string on failure."""
    try:
        if not semantic_query and not edge_type_filter and not node_type:
            return "Error: provide at least one of semantic_query, edge_type_filter, or node_type."

        user_uuid = uuid.UUID(user_id)

        async with AsyncSessionLocal() as session:
            if semantic_query:
                # Semantic search path
                embedding = await get_embedding(semantic_query, task_type="RETRIEVAL_QUERY")
                nodes = await search_nodes_semantic(
                    session, user_uuid, embedding,
                    limit=hp("retrieval", "semantic_search_limit", 15),
                    node_type=node_type,
                )
            else:
                # Structural query — no embedding API call needed
                nodes = await search_nodes_by_edge_structure(
                    session, user_uuid,
                    edge_type=edge_type_filter,
                    node_type=node_type,
                    limit=hp("retrieval", "structural_search_limit", 25),
                )

            # Graph walk: expand results by traversing N hops from matched nodes
            max_depth = int(hp("retrieval", "graph_walk_hops", 2))
            effective_depth = min(depth, max_depth)
            if effective_depth > 0:
                seen_ids = {n.id for n in nodes}
                neighborhoods = await asyncio.gather(*[
                    get_node_neighborhood(session, n.id, user_id=user_uuid, hops=effective_depth)
                    for n in list(nodes)
                ])
                for neighborhood_nodes, _ in neighborhoods:
                    for n in neighborhood_nodes:
                        if n.id not in seen_ids:
                            nodes.append(n)
                            seen_ids.add(n.id)

            # Batch-fetch all edges for all matched nodes in one query (avoids N+1)
            all_node_ids = [n.id for n in nodes]
            edge_fetch_limit = int(hp("retrieval", "edge_fetch_limit", 30))
            all_edges_result = (await session.execute(
                select(GraphEdge).where(
                    GraphEdge.user_id == user_uuid,
                    GraphEdge.source_node_id.in_(all_node_ids),
                )
            )).scalars().all()

            # Group edges by source node, respecting per-node limit
            edges_by_source: dict[uuid.UUID, list[GraphEdge]] = defaultdict(list)
            for e in all_edges_result:
                if len(edges_by_source[e.source_node_id]) < edge_fetch_limit:
                    edges_by_source[e.source_node_id].append(e)

            # Batch-fetch all target nodes referenced by any edge
            all_target_ids = {e.target_node_id for e in all_edges_result}
            target_map: dict[uuid.UUID, str] = {}
            if all_target_ids:
                target_nodes = (await session.execute(
                    select(GraphNode).where(GraphNode.id.in_(all_target_ids))
                )).scalars().all()
                target_map = {t.id: t.content for t in target_nodes}

            # Parse date filters once, not per-node
            from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
            to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

            results = []
            for node in nodes:
                node_edges = edges_by_source.get(node.id, [])

                # Post-filter by edge type when both semantic + structural filters are active
                if semantic_query and edge_type_filter:
                    if not any(e.edge_type == edge_type_filter for e in node_edges):
                        continue

                # Apply temporal filtering
                if from_dt or to_dt:
                    has_matching_date = False
                    for e in node_edges:
                        edge_date = (e.metadata_ or {}).get("date") or (e.metadata_ or {}).get("logged_at")
                        if edge_date:
                            try:
                                edge_dt = datetime.fromisoformat(edge_date.replace("Z", "+00:00"))
                                if from_dt and edge_dt < from_dt:
                                    continue
                                if to_dt and edge_dt > to_dt:
                                    continue
                                has_matching_date = True
                            except (ValueError, TypeError):
                                pass
                    if not has_matching_date:
                        continue

                # Build humanized edge descriptions
                edge_display_limit = int(hp("retrieval", "edge_display_limit", 10))
                edge_details = []
                for e in node_edges[:edge_display_limit]:
                    target_content = target_map.get(e.target_node_id, "")
                    if e.edge_type == "IS_STATUS" and target_content:
                        edge_details.append(f"status: {target_content.lower()}")
                    elif e.edge_type == "HAS_DEADLINE":
                        date = (e.metadata_ or {}).get("date", "")
                        edge_details.append(f"due: {date}" if date else "has deadline")
                    elif e.edge_type == "TRACKS_METRIC":
                        val = (e.metadata_ or {}).get("value", "")
                        unit = (e.metadata_ or {}).get("unit", "")
                        edge_details.append(f"{val} {unit}".strip() if val else "tracked")
                    elif e.edge_type == "DEPENDS_ON" and target_content:
                        edge_details.append(f"depends on: {target_content}")
                    elif e.edge_type == "PART_OF" and target_content:
                        edge_details.append(f"part of: {target_content}")
                    elif target_content:
                        edge_details.append(f"related: {target_content}")

                results.append({
                    "id": str(node.id),
                    "item": node.content,
                    "kind": node.node_type,
                    "details": ", ".join(edge_details) if edge_details else None,
                })

            if not results:
                # Helpful empty-result message
                total_stmt = select(func.count(GraphNode.id)).where(
                    GraphNode.user_id == user_uuid
                )
                total = (await session.execute(total_stmt)).scalar() or 0
                if total == 0:
                    return "Nothing tracked yet."
                return f"Nothing matching that search. You have {total} items tracked."

            return results
    except Exception as e:
        logger.error("query_graph.failed", error=str(e), exc_info=True)
        return _sanitize_error(e)


async def _exec_mutate_graph(
    user_id: str,
    action: str,
    node_id: str,
    value: str | None = None,
    target_node_id: str | None = None,
    edge_type: str | None = None,
) -> str:
    try:
        user_uuid = uuid.UUID(user_id)
        node_uuid = uuid.UUID(node_id)

        async with AsyncSessionLocal() as session:
            if action == "SET_STATUS":
                if value not in ("OPEN", "DONE"):
                    return "Error: value must be 'OPEN' or 'DONE'."
                await update_status_event(session, user_uuid, node_uuid, value)
                await session.commit()
                return f"Status updated to {value}."

            elif action == "ADD_EDGE":
                if not target_node_id or not edge_type:
                    return "Error: ADD_EDGE requires target_node_id and edge_type."
                target_uuid = uuid.UUID(target_node_id)
                metadata = {}
                if value:
                    metadata["value"] = value
                await upsert_edge(
                    session, user_uuid, node_uuid, target_uuid, edge_type, metadata,
                )
                await session.commit()
                return f"Edge {edge_type} added."

            elif action == "REMOVE_EDGE":
                if not target_node_id or not edge_type:
                    return "Error: REMOVE_EDGE requires target_node_id and edge_type."
                target_uuid = uuid.UUID(target_node_id)
                removed = await remove_edge_event(
                    session, user_uuid, node_uuid, target_uuid, edge_type,
                )
                await session.commit()
                return "Edge removed." if removed else "Edge not found."

            elif action == "UPDATE_CONTENT":
                if not value:
                    return "Error: UPDATE_CONTENT requires value (new content)."
                await update_content_event(session, user_uuid, node_uuid, value)
                await session.commit()
                return "Content updated."

            elif action == "ARCHIVE":
                await archive_node_event(session, user_uuid, node_uuid)
                await session.commit()
                return "Node archived."

            else:
                return f"Error: Unknown action '{action}'. Use SET_STATUS, ADD_EDGE, REMOVE_EDGE, UPDATE_CONTENT, or ARCHIVE."

    except Exception as e:
        logger.error("mutate_graph.failed", error=str(e), exc_info=True)
        return _sanitize_error(e)


async def _exec_schedule_reminder(
    user_id: str,
    reminder_text: str,
    remind_at: str,
) -> str:
    """Schedule a reminder using existing ScheduledAction + QStash infrastructure."""
    try:
        remind_dt = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
        if remind_dt.tzinfo is None:
            remind_dt = remind_dt.replace(tzinfo=tz.utc)

        if remind_dt <= datetime.now(tz.utc):
            return "Error: reminder time must be in the future."

        from src.db.queries import save_scheduled_action
        from src.integrations.qstash import dispatch_at
        from src.db.queries import mark_action_dispatched

        action = await save_scheduled_action(
            user_id=user_id,
            action_type="reminder",
            execute_at=remind_dt,
            payload={"text": reminder_text},
        )

        # Dispatch to QStash for delivery at the right time
        msg_id = await dispatch_at(
            "execute-action",
            {"action_ids": [action["id"]]},
            deliver_at=remind_dt,
        )

        if msg_id:
            await mark_action_dispatched(action["id"], msg_id)

        return f"Reminder set for {remind_dt.strftime('%B %d at %H:%M %Z')}."

    except ValueError as e:
        return f"Error: invalid time format — {e}"
    except Exception as e:
        logger.error("schedule_reminder.failed", error=str(e), exc_info=True)
        return _sanitize_error(e)


async def _exec_get_metrics(
    user_id: str,
    metric_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]] | str:
    """Pre-aggregated metric query — returns totals, counts, averages."""
    try:
        from src.db.queries import get_metric_aggregates

        rows = await get_metric_aggregates(
            user_id=user_id,
            metric_name=metric_name,
            date_from=date_from,
            date_to=date_to,
        )

        if not rows:
            if metric_name:
                return f"No entries found for metric '{metric_name}' in the specified date range."
            return "No metrics tracked yet."

        results = []
        for row in rows:
            entry = {
                "metric": row["metric_name"],
                "entry_count": row["entry_count"],
                "total": row["total"],
                "average": row["avg_value"],
                "min": row["min_value"],
                "max": row["max_value"],
                "latest_value": row["latest_value"],
                "unit": row["unit"] or "",
                "date_range": f"{row['earliest_date']} — {row['latest_date']}",
            }
            results.append(entry)

        return results
    except Exception as e:
        logger.error("get_metrics.failed", error=str(e), exc_info=True)
        return _sanitize_error(e)
