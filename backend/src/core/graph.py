"""Graph operations — event-first writes with projection, read queries on projection tables."""

import uuid
from typing import Any

from sqlalchemy import select, and_, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EventStream, GraphNode, GraphEdge


# ──────────────────────────── Append Event (core write primitive) ─────

async def append_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> EventStream:
    """Appends an event to the immutable event stream."""
    event = EventStream(user_id=user_id, event_type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    return event


# ──────────────────────────── Write Operations (event-first) ─────────

async def get_or_create_node(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    node_type: str = "concept",
    embedding: list[float] | None = None,
) -> GraphNode:
    """Gets an exact matching node or creates a new one with event."""
    stmt = select(GraphNode).where(
        GraphNode.user_id == user_id,
        GraphNode.content == content,
        GraphNode.node_type == node_type,
    )
    result = await session.execute(stmt)
    node = result.scalar_one_or_none()

    if not node:
        node = GraphNode(
            user_id=user_id,
            content=content,
            node_type=node_type,
            embedding=embedding,
        )
        session.add(node)
        await session.flush()
        await append_event(session, user_id, "NodeCreated", {
            "node_id": str(node.id),
            "content": content,
            "node_type": node_type,
        })

    return node


async def create_node_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    node_type: str = "concept",
    embedding: list[float] | None = None,
) -> GraphNode:
    """Always creates a new node (no dedup). Event-first."""
    node = GraphNode(
        user_id=user_id,
        content=content,
        node_type=node_type,
        embedding=embedding,
    )
    session.add(node)
    await session.flush()
    await append_event(session, user_id, "NodeCreated", {
        "node_id": str(node.id),
        "content": content,
        "node_type": node_type,
    })
    return node


async def upsert_edge(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    edge_type: str,
    metadata: dict[str, Any] | None = None,
    weight: float = 1.0,
) -> GraphEdge:
    """Creates or updates an edge. Event-first."""
    stmt = select(GraphEdge).where(
        GraphEdge.user_id == user_id,
        GraphEdge.source_node_id == source_id,
        GraphEdge.target_node_id == target_id,
        GraphEdge.edge_type == edge_type,
    )
    result = await session.execute(stmt)
    edge = result.scalar_one_or_none()

    if edge:
        edge.weight = weight
        if metadata is not None:
            edge.metadata_ = metadata
        await append_event(session, user_id, "EdgeUpdated", {
            "edge_id": str(edge.id),
            "source_id": str(source_id),
            "target_id": str(target_id),
            "edge_type": edge_type,
            "metadata": metadata,
        })
    else:
        edge = GraphEdge(
            user_id=user_id,
            source_node_id=source_id,
            target_node_id=target_id,
            edge_type=edge_type,
            weight=weight,
            metadata_=metadata or {},
        )
        session.add(edge)
        await session.flush()
        await append_event(session, user_id, "EdgeAdded", {
            "edge_id": str(edge.id),
            "source_id": str(source_id),
            "target_id": str(target_id),
            "edge_type": edge_type,
            "metadata": metadata,
        })

    return edge


async def create_edge_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    edge_type: str,
    metadata: dict[str, Any] | None = None,
    weight: float = 1.0,
) -> GraphEdge:
    """Alias for upsert_edge — always event-first."""
    return await upsert_edge(session, user_id, source_id, target_id, edge_type, metadata, weight)


async def update_status_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
    new_status: str,
) -> GraphEdge:
    """Update a node's IS_STATUS edge. Event-first."""
    status_node = await get_or_create_node(session, user_id, new_status, "system_status")

    # Remove existing IS_STATUS edge(s) from this node
    existing = await session.execute(
        select(GraphEdge).where(
            GraphEdge.user_id == user_id,
            GraphEdge.source_node_id == node_id,
            GraphEdge.edge_type == "IS_STATUS",
        )
    )
    for old_edge in existing.scalars().all():
        await session.delete(old_edge)

    await append_event(session, user_id, "StatusUpdated", {
        "node_id": str(node_id),
        "new_status": new_status,
    })

    edge = await upsert_edge(session, user_id, node_id, status_node.id, "IS_STATUS")
    return edge


async def update_content_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
    new_content: str,
) -> GraphNode:
    """Update a node's content. Event-first."""
    node = await session.get(GraphNode, node_id)
    if not node or node.user_id != user_id:
        raise ValueError(f"Node {node_id} not found for user {user_id}")

    old_content = node.content
    node.content = new_content

    await append_event(session, user_id, "ContentUpdated", {
        "node_id": str(node_id),
        "old_content": old_content,
        "new_content": new_content,
    })
    return node


async def archive_node_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> GraphNode:
    """Archive a node (change type to archived_*). Event-first."""
    node = await session.get(GraphNode, node_id)
    if not node or node.user_id != user_id:
        raise ValueError(f"Node {node_id} not found for user {user_id}")

    if not node.node_type.startswith("archived_"):
        node.node_type = f"archived_{node.node_type}"

    await append_event(session, user_id, "NodeArchived", {
        "node_id": str(node_id),
        "content": node.content,
    })
    return node


async def delete_node_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> None:
    """Delete a node and its edges. Event-first."""
    node = await session.get(GraphNode, node_id)
    if not node or node.user_id != user_id:
        raise ValueError(f"Node {node_id} not found for user {user_id}")

    await append_event(session, user_id, "NodeDeleted", {
        "node_id": str(node_id),
        "content": node.content,
    })

    # Delete edges (scoped to user)
    await session.execute(
        delete(GraphEdge).where(
            and_(
                GraphEdge.user_id == user_id,
                (GraphEdge.source_node_id == node_id) | (GraphEdge.target_node_id == node_id),
            )
        )
    )
    await session.delete(node)


async def remove_edge_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    edge_type: str,
) -> bool:
    """Remove a specific edge. Event-first. Returns True if found and removed."""
    stmt = select(GraphEdge).where(
        GraphEdge.user_id == user_id,
        GraphEdge.source_node_id == source_id,
        GraphEdge.target_node_id == target_id,
        GraphEdge.edge_type == edge_type,
    )
    result = await session.execute(stmt)
    edge = result.scalar_one_or_none()
    if not edge:
        return False

    await append_event(session, user_id, "EdgeRemoved", {
        "edge_id": str(edge.id),
        "source_id": str(source_id),
        "target_id": str(target_id),
        "edge_type": edge_type,
    })
    await session.delete(edge)
    return True


# ──────────────────────────── Read Operations ────────────────────────

async def search_nodes_semantic(
    session: AsyncSession,
    user_id: uuid.UUID,
    embedding: list[float],
    limit: int = 5,
    node_type: str | None = None,
    max_distance: float | None = None,
) -> list[GraphNode]:
    """Semantic vector search via pgvector cosine distance.

    Args:
        max_distance: If set, only return nodes whose cosine distance is
            *at most* this value.  Cosine distance ranges 0 (identical) to 2
            (opposite).  A ``max_distance`` of 0.1 corresponds to cosine
            similarity >= 0.9.
    """
    distance_expr = GraphNode.embedding.cosine_distance(embedding)

    stmt = select(GraphNode).where(
        GraphNode.user_id == user_id,
        GraphNode.embedding.isnot(None),
    )
    if node_type:
        stmt = stmt.where(GraphNode.node_type == node_type)
    if max_distance is not None:
        stmt = stmt.where(distance_expr <= max_distance)

    stmt = stmt.order_by(distance_expr).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search_nodes_by_edge_structure(
    session: AsyncSession,
    user_id: uuid.UUID,
    edge_type: str | None = None,
    node_type: str | None = None,
    limit: int = 20,
) -> list[GraphNode]:
    """Find nodes by edge type and/or node type."""
    stmt = select(GraphNode).where(GraphNode.user_id == user_id)

    if node_type:
        stmt = stmt.where(GraphNode.node_type == node_type)

    if edge_type:
        stmt = stmt.where(
            GraphNode.id.in_(
                select(GraphEdge.source_node_id).where(
                    GraphEdge.user_id == user_id,
                    GraphEdge.edge_type == edge_type,
                )
            )
        )

    stmt = stmt.order_by(GraphNode.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_node_neighborhood(
    session: AsyncSession,
    node_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    hops: int = 1,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Get a node's immediate neighborhood (nodes + edges within N hops)."""
    visited_node_ids: set[uuid.UUID] = {node_id}
    all_edges: list[GraphEdge] = []

    current_ids = {node_id}
    for _ in range(hops):
        if not current_ids:
            break

        edges_stmt = select(GraphEdge).where(
            (GraphEdge.source_node_id.in_(current_ids)) |
            (GraphEdge.target_node_id.in_(current_ids))
        )
        if user_id is not None:
            edges_stmt = edges_stmt.where(GraphEdge.user_id == user_id)
        result = await session.execute(edges_stmt)
        edges = list(result.scalars().all())
        all_edges.extend(edges)

        next_ids: set[uuid.UUID] = set()
        for e in edges:
            next_ids.add(e.source_node_id)
            next_ids.add(e.target_node_id)
        next_ids -= visited_node_ids
        visited_node_ids |= next_ids
        current_ids = next_ids

    # Fetch all nodes
    if visited_node_ids:
        nodes_stmt = select(GraphNode).where(GraphNode.id.in_(visited_node_ids))
        if user_id is not None:
            nodes_stmt = nodes_stmt.where(GraphNode.user_id == user_id)
        result = await session.execute(nodes_stmt)
        nodes = list(result.scalars().all())
    else:
        nodes = []

    return nodes, all_edges


async def get_nodes_by_ids(
    session: AsyncSession,
    node_ids: list[uuid.UUID],
) -> list[GraphNode]:
    """Fetch nodes by their IDs."""
    if not node_ids:
        return []
    stmt = select(GraphNode).where(GraphNode.id.in_(node_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_edges_for_nodes(
    session: AsyncSession,
    node_ids: list[uuid.UUID],
    user_id: uuid.UUID | None = None,
) -> list[GraphEdge]:
    """Get all edges where source or target is in the given node IDs."""
    if not node_ids:
        return []
    stmt = select(GraphEdge).where(
        (GraphEdge.source_node_id.in_(node_ids)) |
        (GraphEdge.target_node_id.in_(node_ids))
    )
    if user_id is not None:
        stmt = stmt.where(GraphEdge.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
