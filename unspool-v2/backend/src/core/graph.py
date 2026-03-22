from typing import Any, Dict, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update

from src.core.models import EventStream, GraphNode, GraphEdge

async def append_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    payload: Dict[str, Any]
) -> EventStream:
    """Appends an event to the immutable event stream."""
    event = EventStream(
        user_id=user_id,
        event_type=event_type,
        payload=payload
    )
    session.add(event)
    await session.flush()  # Get ID without committing
    return event

async def get_or_create_node(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    node_type: str = "concept",
    embedding: Optional[list[float]] = None
) -> GraphNode:
    """Gets an exact matching node or creates a new one."""
    stmt = select(GraphNode).where(
        GraphNode.user_id == user_id,
        GraphNode.content == content,
        GraphNode.node_type == node_type
    )
    result = await session.execute(stmt)
    node = result.scalar_one_or_none()

    if not node:
        node = GraphNode(
            user_id=user_id,
            content=content,
            node_type=node_type,
            embedding=embedding
        )
        session.add(node)
        await session.flush()
        
        # Track the creation in the event stream
        await append_event(session, user_id, "NodeCreated", {
            "node_id": str(node.id),
            "content": content,
            "node_type": node_type
        })
        
    return node

async def upsert_edge(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    edge_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    weight: float = 1.0
) -> GraphEdge:
    """Creates or updates an edge between two nodes."""
    stmt = select(GraphEdge).where(
        GraphEdge.user_id == user_id,
        GraphEdge.source_node_id == source_id,
        GraphEdge.target_node_id == target_id,
        GraphEdge.edge_type == edge_type
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
            "metadata": metadata
        })
    else:
        edge = GraphEdge(
            user_id=user_id,
            source_node_id=source_id,
            target_node_id=target_id,
            edge_type=edge_type,
            weight=weight,
            metadata_=metadata or {}
        )
        session.add(edge)
        await session.flush()
        
        await append_event(session, user_id, "EdgeCreated", {
            "edge_id": str(edge.id),
            "source_id": str(source_id),
            "target_id": str(target_id),
            "edge_type": edge_type,
            "metadata": metadata
        })

    return edge

async def search_nodes_semantic(
    session: AsyncSession,
    user_id: uuid.UUID,
    embedding: list[float],
    limit: int = 5
):
    """Performs an HNSW vector search using pgvector."""
    # <-> is the L2 distance, <=_cosine=> is cosine similarity
    stmt = select(GraphNode).where(
        GraphNode.user_id == user_id
    ).order_by(
        GraphNode.embedding.cosine_distance(embedding)
    ).limit(limit)
    
    result = await session.execute(stmt)
    return result.scalars().all()
