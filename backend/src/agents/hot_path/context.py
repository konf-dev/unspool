"""Context assembly for the hot path — parallel loads of profile, messages, graph, deadlines."""

import asyncio
import uuid
from typing import Any

from src.core.database import AsyncSessionLocal
from src.core.graph import search_nodes_semantic, get_node_neighborhood
from src.db.queries import get_messages_from_events, get_profile
from src.integrations.gemini import get_embedding
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("agent.context")


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
    deadline_context: str = ""

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

                # Expand neighborhoods for top 3 results
                all_node_ids = set()
                all_edges = []
                for node in nodes[:3]:
                    neighborhood_nodes, neighborhood_edges = await get_node_neighborhood(
                        session, node.id, hops=1
                    )
                    all_node_ids.update(n.id for n in neighborhood_nodes)
                    all_edges.extend(neighborhood_edges)

                # Serialize into readable format
                lines = []
                seen_node_ids = set()
                for node in nodes:
                    if node.id in seen_node_ids:
                        continue
                    seen_node_ids.add(node.id)
                    # Get edges for this node
                    node_edges = [e for e in all_edges if e.source_node_id == node.id]
                    edge_strs = []
                    for e in node_edges[:3]:
                        edge_strs.append(f"{e.edge_type}")
                    edge_info = f" [{', '.join(edge_strs)}]" if edge_strs else ""
                    lines.append(f"- {node.content} ({node.node_type}){edge_info}")

                if lines:
                    graph_context = "Relevant memories:\n" + "\n".join(lines[:15])
        except Exception as e:
            report_error("context.graph_failed", e, user_id=user_id)

    async def _load_deadlines() -> None:
        nonlocal deadline_context
        try:
            from src.db.queries import get_proactive_items
            items = await get_proactive_items(user_id, hours=72)
            if items:
                lines = []
                for item in items[:5]:
                    lines.append(f"- {item['content']} (due: {item['deadline']})")
                deadline_context = "Upcoming deadlines:\n" + "\n".join(lines)
        except Exception as e:
            report_error("context.deadlines_failed", e, user_id=user_id)

    await asyncio.gather(
        _load_profile(),
        _load_messages(),
        _load_graph(),
        _load_deadlines(),
        return_exceptions=True,
    )

    # Build context block
    sections: list[str] = []
    if graph_context:
        sections.append(graph_context)
    if deadline_context:
        sections.append(deadline_context)

    context_block = ""
    if sections:
        context_block = "<context>\n" + "\n\n".join(sections) + "\n</context>"

    _log.info(
        "context.assembled",
        trace_id=trace_id,
        has_graph=bool(graph_context),
        has_deadlines=bool(deadline_context),
        message_count=len(recent_messages),
    )

    return context_block, profile, recent_messages
