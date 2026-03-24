"""Hot path tools — query_graph and mutate_graph.

user_id is NOT a tool parameter — it's injected from LangGraph state in call_tools.
"""

import uuid
from typing import Any

from sqlalchemy import select, and_

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


@tool
async def query_graph(
    semantic_query: str,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
) -> list[dict[str, Any]]:
    """Searches the user's memory graph for nodes matching the query.

    Args:
        semantic_query: The concept or task to search for (e.g., 'Mom', 'Thesis deadlines').
        edge_type_filter: Optional. Only returns nodes with this edge type (e.g. 'HAS_DEADLINE', 'IS_STATUS').
        node_type: Optional. Filter by node type (e.g. 'action', 'concept', 'person').
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


# Actual implementations called by call_tools with user_id injected

async def _exec_query_graph(
    user_id: str,
    semantic_query: str,
    edge_type_filter: str | None = None,
    node_type: str | None = None,
) -> list[dict[str, Any]]:
    try:
        user_uuid = uuid.UUID(user_id)
        embedding = await get_embedding(semantic_query, task_type="RETRIEVAL_QUERY")

        async with AsyncSessionLocal() as session:
            nodes = await search_nodes_semantic(
                session, user_uuid, embedding, limit=8, node_type=node_type,
            )

            results = []
            for node in nodes:
                if edge_type_filter:
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

                # Get immediate edges (up to 3) for context
                edge_stmt = select(GraphEdge).where(
                    GraphEdge.source_node_id == node.id
                ).limit(3)
                node_edges = (await session.execute(edge_stmt)).scalars().all()

                edge_info = []
                for e in node_edges:
                    target = await session.get(GraphNode, e.target_node_id)
                    target_content = target.content if target else "?"
                    edge_info.append({
                        "type": e.edge_type,
                        "target": target_content,
                        "metadata": e.metadata_,
                    })

                results.append({
                    "id": str(node.id),
                    "content": node.content,
                    "type": node.node_type,
                    "edges": edge_info,
                })

            return results
    except Exception as e:
        logger.error("query_graph.failed", error=str(e), exc_info=True)
        return [{"error": str(e)}]


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
        return f"Error: {str(e)}"
