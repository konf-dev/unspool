"""Graph memory context loader — retrieves and serializes graph context."""

from src.llm.embedding import OpenAIEmbedding
from src.orchestrator.config_loader import load_config
from src.telemetry.logger import get_logger
from src.tools.registry import register_tool

_log = get_logger("tools.graph")


@register_tool("fetch_graph_context")
async def fetch_graph_context(user_id: str, message: str = "") -> str | None:
    """Build graph context for the current message.

    Returns serialized context string, or None if graph is empty/unavailable.
    """
    try:
        from src.graph.retrieval import build_active_subgraph
        from src.graph.serialization import serialize_subgraph
    except ImportError:
        _log.debug("graph.module_not_available")
        return None

    try:
        # Check if graph tables exist by attempting a lightweight query
        from src.graph import db as graph_db

        stats = await graph_db.get_graph_stats(user_id)
        if not stats or stats.get("nodes", 0) == 0:
            return None
    except Exception:
        _log.debug("graph.tables_not_ready")
        return None

    graph_config = load_config("graph")
    shadow_mode = graph_config.get("shadow_mode", True)

    message_embedding = None
    if message:
        try:
            embedder = OpenAIEmbedding()
            message_embedding = await embedder.embed(message)
        except Exception:
            _log.warning("graph.embedding_failed")

    try:
        subgraph = await build_active_subgraph(
            user_id=user_id,
            message=message,
            message_embedding=message_embedding,
            quick_nodes=[],
        )

        if not subgraph.nodes:
            return None

        serialized = serialize_subgraph(subgraph)

        _log.info(
            "graph.retrieval.done",
            user_id=user_id,
            triggers_fired=len(subgraph.trigger_results),
            nodes_in_subgraph=len(subgraph.nodes),
            edges_in_subgraph=len(subgraph.edges),
            shadow_mode=shadow_mode,
        )

        if shadow_mode:
            _log.info(
                "graph.shadow_context",
                user_id=user_id,
                context_length=len(serialized),
            )
            return None

        return serialized

    except Exception:
        _log.warning("graph.retrieval.failed", user_id=user_id, exc_info=True)
        return None
