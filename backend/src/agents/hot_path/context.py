"""Context assembly for the hot path — parallel loads of profile, messages, graph, structured data."""

import asyncio
import uuid
from typing import Any

from src.core.database import AsyncSessionLocal
from src.core.graph import search_nodes_semantic, get_node_neighborhood
from src.db.queries import (
    get_messages_from_events,
    get_plate_items,
    get_profile,
    get_proactive_items,
    get_recently_done_count,
)
from src.integrations.gemini import get_embedding
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("agent.context")


def _extract_recent_mentions(messages: list[dict[str, Any]]) -> str:
    """Extract user mentions from recent messages not yet in graph (cold path delay)."""
    lines = []
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            content = str(msg["content"]).strip()
            if content and len(content) < 200:
                lines.append(f"  - {content}")
    return "\n".join(lines[-3:]) if lines else ""


@observe(name="agent.assemble_context")
async def assemble_context(
    user_id: str,
    message: str,
    trace_id: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Assemble context for the agent.

    Returns: (context_block, profile, recent_messages)
    """
    profile: dict[str, Any] = {}
    recent_messages: list[dict[str, Any]] = []
    graph_context: str = ""
    structured_context: str = ""

    async def _load_profile() -> None:
        nonlocal profile
        try:
            p = await get_profile(user_id)
            if p:
                profile = p
        except Exception as e:
            report_error("context.profile_failed", e, user_id=user_id)

    async def _load_messages() -> None:
        nonlocal recent_messages
        try:
            async with AsyncSessionLocal() as session:
                msgs = await get_messages_from_events(session, user_id, limit=20)
                recent_messages = list(reversed(msgs))
        except Exception as e:
            report_error("context.messages_failed", e, user_id=user_id)

    async def _load_graph() -> None:
        nonlocal graph_context
        try:
            embedding = await get_embedding(message, task_type="RETRIEVAL_QUERY")
            async with AsyncSessionLocal() as session:
                user_uuid = uuid.UUID(user_id)
                nodes = await search_nodes_semantic(session, user_uuid, embedding, limit=10)
                if not nodes:
                    return

                # Parallelize neighborhood expansion — each gets its own session
                # because AsyncSession is not safe for concurrent use.
                async def _get_neighborhood(node_id: uuid.UUID) -> tuple:
                    async with AsyncSessionLocal() as s:
                        return await get_node_neighborhood(s, node_id, user_id=user_uuid, hops=1)

                neighborhoods = await asyncio.gather(*[
                    _get_neighborhood(node.id)
                    for node in nodes[:3]
                ])
                all_neighborhood_nodes: list[Any] = []
                all_edges: list[Any] = []
                for n_nodes, n_edges in neighborhoods:
                    all_neighborhood_nodes.extend(n_nodes)
                    all_edges.extend(n_edges)

                # Deduplicate edges from overlapping neighborhoods
                seen_edge_ids: set[uuid.UUID] = set()
                deduped_edges: list[Any] = []
                for e in all_edges:
                    if e.id not in seen_edge_ids:
                        seen_edge_ids.add(e.id)
                        deduped_edges.append(e)
                all_edges = deduped_edges

                # Serialize into human-readable linearized format
                lines = []
                seen_node_ids: set[uuid.UUID] = set()
                for node in nodes:
                    if node.id in seen_node_ids:
                        continue
                    seen_node_ids.add(node.id)
                    node_edges = [e for e in all_edges if e.source_node_id == node.id]
                    edge_strs = []
                    for e in node_edges[:3]:
                        target = next(
                            (n for n in all_neighborhood_nodes if n.id == e.target_node_id),
                            None,
                        )
                        if e.edge_type == "IS_STATUS" and target:
                            edge_strs.append(f"status: {target.content.lower()}")
                        elif e.edge_type == "HAS_DEADLINE":
                            date = (e.metadata_ or {}).get("date", "")
                            edge_strs.append(f"due: {date[:10]}" if date else "has deadline")
                        elif e.edge_type == "TRACKS_METRIC":
                            val = (e.metadata_ or {}).get("value", "")
                            unit = (e.metadata_ or {}).get("unit", "")
                            edge_strs.append(f"{val} {unit}".strip() if val else "tracked")
                        elif e.edge_type == "DEPENDS_ON" and target:
                            edge_strs.append(f"depends on: {target.content}")
                        elif target:
                            edge_strs.append(f"related: {target.content}")
                    edge_info = f" — {', '.join(edge_strs)}" if edge_strs else ""
                    lines.append(f"- {node.content}{edge_info}")

                if lines:
                    graph_context = "\n".join(lines[:15])
        except Exception as e:
            report_error("context.graph_failed", e, user_id=user_id)

    async def _load_structured_items() -> None:
        """Load deterministic structured data — open items, deadlines, recent completions."""
        nonlocal structured_context
        sections = []

        try:
            plate = await get_plate_items(user_id)
            if plate:
                lines = []
                for item in plate:
                    parts = [item["content"]]
                    if item.get("deadline"):
                        parts.append(f"due: {str(item['deadline'])[:10]}")
                    lines.append(f"  - {' — '.join(parts)}")
                sections.append(f"Open items ({len(plate)}):\n" + "\n".join(lines))

            # Imminent deadlines (next 48h)
            imminent = await get_proactive_items(user_id, hours=48)
            if imminent:
                lines = [f"  - {i['content']} (due: {str(i['deadline'])[:10]})" for i in imminent]
                sections.append("Due soon:\n" + "\n".join(lines))

            # Recent completions (momentum signal)
            done_count = await get_recently_done_count(user_id, hours=48)
            if done_count > 0:
                sections.append(f"Recently completed: {done_count} item{'s' if done_count != 1 else ''} in the last 48h.")

        except Exception as e:
            report_error("context.structured_failed", e, user_id=user_id)

        if sections:
            structured_context = "\n\n".join(sections)

    await asyncio.gather(
        _load_profile(),
        _load_messages(),
        _load_graph(),
        _load_structured_items(),
        return_exceptions=True,
    )

    # Build hierarchical context block
    context_block = ""
    sections: list[str] = []

    # Tier 1: Structured (deterministic, always accurate)
    if structured_context:
        sections.append(structured_context)

    # Tier 2: Semantic (relevant memories from graph search)
    if graph_context:
        sections.append("Related memories:\n" + graph_context)

    # Tier 3: Temporal (conversation continuity — recent mentions not yet in graph)
    recent_mentions = _extract_recent_mentions(recent_messages[-3:])
    if recent_mentions:
        sections.append("Just mentioned:\n" + recent_mentions)

    if sections:
        context_block = "<context>\n" + "\n\n".join(sections) + "\n</context>"

    _log.info(
        "context.assembled",
        trace_id=trace_id,
        has_graph=bool(graph_context),
        has_structured=bool(structured_context),
        message_count=len(recent_messages),
    )

    return context_block, profile, recent_messages
