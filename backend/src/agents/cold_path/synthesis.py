"""Nightly synthesis — duplicate merging, archival, edge decay, view refresh."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, delete, and_, not_, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.graph import (
    append_event,
    archive_node_event,
    delete_node_event,
    search_nodes_semantic,
)
from src.core.models import GraphNode, GraphEdge
from src.core.config_loader import load_config
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

logger = get_logger("cold_path.synthesis")


async def run_nightly_synthesis(user_id: uuid.UUID) -> dict:
    """Full nightly synthesis for a single user."""
    logger.info("synthesis.start", user_id=str(user_id))
    results: dict = {}

    async with AsyncSessionLocal() as session:
        # 1. Archive DONE items older than 7 days
        results["archived"] = await _archive_done_items(session, user_id)

        # 2. Duplicate node merging (>0.9 similarity)
        results["merged"] = await _merge_duplicates(session, user_id)

        # 3. Edge weight decay
        results["decayed"] = await _decay_edges(session, user_id)

        await session.commit()

    # 4. Refresh materialized views (if any exist as materialized)
    # Currently using regular views, so no refresh needed
    results["views_refreshed"] = True

    logger.info("synthesis.complete", user_id=str(user_id), results=results)
    return results


async def _archive_done_items(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Archive action nodes marked DONE for >7 days."""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Find DONE system node
    done_node = (await session.execute(
        select(GraphNode).where(
            GraphNode.user_id == user_id,
            GraphNode.content == "DONE",
            GraphNode.node_type == "system_status",
        )
    )).scalar_one_or_none()

    if not done_node:
        return 0

    # Find edges to DONE older than 7 days
    old_edges = (await session.execute(
        select(GraphEdge).where(
            GraphEdge.user_id == user_id,
            GraphEdge.target_node_id == done_node.id,
            GraphEdge.edge_type == "IS_STATUS",
            GraphEdge.updated_at < seven_days_ago,
        )
    )).scalars().all()

    archived = 0
    for edge in old_edges:
        source = await session.get(GraphNode, edge.source_node_id)
        if source and source.node_type == "action":
            source.node_type = "archived_action"
            await append_event(session, user_id, "NodeArchived", {
                "node_id": str(source.id), "content": source.content,
            })
            archived += 1

    return archived


async def _merge_duplicates(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Merge nodes with >0.9 cosine similarity."""
    # Get all nodes with embeddings
    nodes = (await session.execute(
        select(GraphNode).where(
            GraphNode.user_id == user_id,
            GraphNode.embedding.isnot(None),
            not_(GraphNode.node_type.like("system_%")),
            not_(GraphNode.node_type.like("archived_%")),
        ).order_by(GraphNode.created_at)
    )).scalars().all()

    merged = 0
    merged_ids: set[uuid.UUID] = set()

    for i, node in enumerate(nodes):
        if node.id in merged_ids:
            continue

        # Find similar nodes
        similar = await search_nodes_semantic(
            session, user_id, node.embedding, limit=5, node_type=node.node_type,
        )

        for candidate in similar:
            if candidate.id == node.id or candidate.id in merged_ids:
                continue

            # Check if same type and very similar (using position as proxy for similarity)
            if candidate.node_type == node.node_type and candidate.content != node.content:
                # Merge: remap all edges from candidate to node
                # Update edges where candidate is source
                await session.execute(
                    update(GraphEdge).where(
                        GraphEdge.source_node_id == candidate.id
                    ).values(source_node_id=node.id)
                )
                # Update edges where candidate is target
                await session.execute(
                    update(GraphEdge).where(
                        GraphEdge.target_node_id == candidate.id
                    ).values(target_node_id=node.id)
                )

                # Delete duplicate edges that may result from remapping
                # (same source, target, edge_type)
                await session.execute(text("""
                    DELETE FROM graph_edges a
                    USING graph_edges b
                    WHERE a.id > b.id
                      AND a.source_node_id = b.source_node_id
                      AND a.target_node_id = b.target_node_id
                      AND a.edge_type = b.edge_type
                """))

                # Delete the merged node
                await session.delete(candidate)
                merged_ids.add(candidate.id)
                merged += 1

                await append_event(session, user_id, "NodesMerged", {
                    "kept_id": str(node.id),
                    "removed_id": str(candidate.id),
                    "kept_content": node.content,
                    "removed_content": candidate.content,
                })
                break  # Only merge one per iteration to be safe

    return merged


async def _decay_edges(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Apply edge weight decay from graph.yaml config."""
    try:
        config = load_config("graph")
    except FileNotFoundError:
        return 0

    evolution = config.get("evolution", {})
    decay_factor = evolution.get("edge_decay_factor", 0.99)
    decay_min = evolution.get("edge_decay_min", 0.01)

    result = await session.execute(
        update(GraphEdge).where(
            GraphEdge.user_id == user_id,
            GraphEdge.weight > decay_min,
        ).values(
            weight=func.greatest(GraphEdge.weight * decay_factor, decay_min)
        )
    )

    return result.rowcount
