"""Hot path tools — query_graph, mutate_graph, schedule_reminder.

user_id is NOT a tool parameter — it's injected from LangGraph state in call_tools.
"""

import uuid
from datetime import datetime, timezone as tz
from typing import Any

from sqlalchemy import select, and_, func

from src.core.database import AsyncSessionLocal
from src.core.graph import (
    search_nodes_semantic,
    search_nodes_by_edge_structure,
    upsert_edge,
    update_status_event,
    update_content_event,
    archive_node_event,
    remove_edge_event,
    get_or_create_node,
)
from src.core.models import GraphNode, GraphEdge
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
) -> list[dict[str, Any]]:
    """Searches the user's memory graph.

    Args:
        semantic_query: Optional search term. If omitted, returns all matching nodes.
        edge_type_filter: Filter by edge type (e.g. 'HAS_DEADLINE', 'IS_STATUS').
        node_type: Filter by node type (e.g. 'action', 'concept', 'person', 'memory').
        date_from: Optional ISO8601 date. Filter results to items with edge dates >= this.
        date_to: Optional ISO8601 date. Filter results to items with edge dates <= this.

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


# Actual implementations called by call_tools with user_id injected

async def _exec_query_graph(
    user_id: str,
    semantic_query: str | None = None,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
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
                    session, user_uuid, embedding, limit=8, node_type=node_type,
                )
            else:
                # Structural query — no embedding API call needed
                nodes = await search_nodes_by_edge_structure(
                    session, user_uuid,
                    edge_type=edge_type_filter,
                    node_type=node_type,
                )

            results = []
            for node in nodes:
                if semantic_query and edge_type_filter:
                    # Post-filter semantic results by edge type
                    stmt = select(GraphEdge).where(
                        and_(
                            GraphEdge.user_id == user_uuid,
                            GraphEdge.source_node_id == node.id,
                            GraphEdge.edge_type == edge_type_filter,
                        )
                    )
                    edges = (await session.execute(stmt)).scalars().all()
                    if not edges:
                        continue

                # Get immediate edges (up to 20 for post-filtering) for context
                edge_stmt = select(GraphEdge).where(
                    GraphEdge.user_id == user_uuid,
                    GraphEdge.source_node_id == node.id,
                ).limit(20)
                node_edges = (await session.execute(edge_stmt)).scalars().all()

                # Apply temporal filtering if date params provided
                if date_from or date_to:
                    has_matching_date = False
                    for e in node_edges:
                        edge_date = (e.metadata_ or {}).get("date") or (e.metadata_ or {}).get("logged_at")
                        if edge_date:
                            try:
                                edge_dt = datetime.fromisoformat(edge_date.replace("Z", "+00:00"))
                                if date_from:
                                    from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                                    if edge_dt < from_dt:
                                        continue
                                if date_to:
                                    to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                                    if edge_dt > to_dt:
                                        continue
                                has_matching_date = True
                            except (ValueError, TypeError):
                                pass
                    if not has_matching_date:
                        continue

                # Batch-fetch all target nodes to avoid N+1
                target_ids = [e.target_node_id for e in node_edges]
                target_map: dict[uuid.UUID, str] = {}
                if target_ids:
                    target_nodes = (await session.execute(
                        select(GraphNode).where(GraphNode.id.in_(target_ids))
                    )).scalars().all()
                    target_map = {t.id: t.content for t in target_nodes}

                # Build humanized edge descriptions (limit display to 5)
                edge_details = []
                for e in node_edges[:5]:
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
