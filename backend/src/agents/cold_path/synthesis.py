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
from src.core.config_loader import hp
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

    # 4. Re-compute actionable flags on stale nodes
    async with AsyncSessionLocal() as session2:
        results["actionable_recomputed"] = await _recompute_actionable_flags(session2, user_id)
        await session2.commit()

    # 5. Refresh materialized views (if any exist as materialized)
    # Currently using regular views, so no refresh needed
    results["views_refreshed"] = True

    logger.info("synthesis.complete", user_id=str(user_id), results=results)
    return results


async def _archive_done_items(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Archive action nodes marked DONE for longer than the configured threshold."""
    archive_days = int(hp("synthesis", "archive_done_after_days", 7))
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=archive_days)

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
        if source and source.node_type in ("action", "memory", "concept"):
            source.node_type = f"archived_{source.node_type}"
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

        similar = await search_nodes_semantic(
            session, user_id, node.embedding,
            limit=int(hp("synthesis", "merge_candidates_limit", 5)),
            node_type=node.node_type,
            max_distance=float(hp("synthesis", "merge_max_distance", 0.15)),
        )

        for candidate in similar:
            if candidate.id == node.id or candidate.id in merged_ids:
                continue

            # A4: never merge nodes that source TRACKS_METRIC edges (metric data points)
            metric_count = (await session.execute(
                select(func.count(GraphEdge.id)).where(
                    GraphEdge.user_id == user_id,
                    GraphEdge.source_node_id.in_([node.id, candidate.id]),
                    GraphEdge.edge_type == "TRACKS_METRIC",
                )
            )).scalar()
            if metric_count:
                continue

            # Check if same type and very similar (using position as proxy for similarity)
            if candidate.node_type == node.node_type and candidate.content != node.content:
                # Merge: remap all edges from candidate to node (scoped to user)
                await session.execute(
                    update(GraphEdge).where(
                        GraphEdge.user_id == user_id,
                        GraphEdge.source_node_id == candidate.id,
                    ).values(source_node_id=node.id)
                )
                await session.execute(
                    update(GraphEdge).where(
                        GraphEdge.user_id == user_id,
                        GraphEdge.target_node_id == candidate.id,
                    ).values(target_node_id=node.id)
                )

                # Delete duplicate edges that may result from remapping
                # (same source, target, edge_type — scoped to user)
                await session.execute(text("""
                    DELETE FROM graph_edges a
                    USING graph_edges b
                    WHERE a.id > b.id
                      AND a.user_id = :uid
                      AND b.user_id = :uid
                      AND a.source_node_id = b.source_node_id
                      AND a.target_node_id = b.target_node_id
                      AND a.edge_type = b.edge_type
                """), {"uid": str(user_id)})

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


async def _recompute_actionable_flags(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Re-compute actionable flags on old nodes whose dates suggest they're stale.

    If a node has temporal.dates that are all in the past and tense is 'future',
    update tense to 'past' and actionable to false.
    """
    from sqlalchemy import text as sa_text
    result = await session.execute(sa_text("""
        UPDATE graph_nodes
        SET metadata = jsonb_set(
            jsonb_set(
                COALESCE(metadata, '{}'),
                '{actionable}', 'false'
            ),
            '{temporal,tense}', '"past"'
        )
        WHERE user_id = :uid
          AND node_type IN ('memory', 'action', 'concept')
          AND COALESCE((metadata->>'actionable')::boolean, true) = true
          AND metadata->'temporal'->>'tense' = 'future'
          AND metadata->'temporal'->'dates' IS NOT NULL
          AND jsonb_array_length(metadata->'temporal'->'dates') > 0
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(metadata->'temporal'->'dates') d
              WHERE d::timestamptz >= NOW()
          )
    """), {"uid": str(user_id)})
    return result.rowcount


async def _decay_edges(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Apply edge weight decay using centralized config."""
    decay_factor = float(hp("synthesis", "edge_decay_factor", 0.99))
    decay_min = float(hp("synthesis", "edge_decay_min", 0.01))

    result = await session.execute(
        update(GraphEdge).where(
            GraphEdge.user_id == user_id,
            GraphEdge.weight > decay_min,
        ).values(
            weight=func.greatest(GraphEdge.weight * decay_factor, decay_min)
        )
    )

    return result.rowcount
