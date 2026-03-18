"""Post-processing job: graph ingest + feedback for a conversation turn."""

from src.db import supabase as supa_db
from src.telemetry.logger import get_logger

_log = get_logger("jobs.process_graph")


async def run_process_graph(user_id: str, message_ids: list[str]) -> dict:
    """Ingest user message into graph and apply feedback from assistant response."""
    stats = {
        "nodes_created": 0,
        "ingest_skipped": False,
        "feedback_applied": False,
    }

    try:
        from src.graph.ingest import quick_ingest
        from src.graph.feedback import detect_feedback, apply_feedback
        from src.graph.retrieval import build_active_subgraph
    except ImportError:
        _log.warning("process_graph.module_not_available")
        return stats

    # Load messages: first is user, second is assistant
    messages = await supa_db.get_messages_by_ids(message_ids)
    user_msg = None
    assistant_msg = None
    for msg in messages:
        if msg.get("role") == "user":
            user_msg = msg
        elif msg.get("role") == "assistant":
            assistant_msg = msg

    if not user_msg:
        _log.warning("process_graph.no_user_message", message_ids=message_ids)
        return stats

    # Phase 1: Ingest user message into graph
    try:
        user_msg_id = str(user_msg["id"])
        user_content = user_msg.get("content", "")
        msg_metadata = user_msg.get("metadata", {})
        msg_timestamp = (
            msg_metadata.get("created_at") if isinstance(msg_metadata, dict) else None
        )

        created_nodes = await quick_ingest(
            user_id=user_id,
            message=user_content,
            message_id=user_msg_id,
            message_timestamp=msg_timestamp,
        )
        stats["nodes_created"] = len(created_nodes)

        if not created_nodes:
            stats["ingest_skipped"] = True

    except Exception:
        _log.warning("process_graph.ingest_failed", user_id=user_id, exc_info=True)

    # Phase 2: Generate embeddings for new nodes (dedup runs in evolution, not per-message)
    try:
        from src.llm.embedding import OpenAIEmbedding
        from src.graph import db as graph_db

        all_nodes = await graph_db.get_all_nodes(user_id)
        unembedded = [n for n in all_nodes if not n.get("embedding")]
        if unembedded:
            embedder = OpenAIEmbedding()
            contents = [n["content"] for n in unembedded]
            embeddings = await embedder.embed_batch(contents)
            for node, emb in zip(unembedded, embeddings):
                await graph_db.update_node_embedding(node["id"], emb)
    except Exception:
        _log.warning("process_graph.embedding_failed", user_id=user_id, exc_info=True)

    # Phase 3: Feedback from assistant response
    if assistant_msg and stats["nodes_created"] > 0:
        try:
            subgraph = await build_active_subgraph(
                user_id=user_id,
                message=user_msg.get("content", ""),
                message_embedding=None,
                quick_nodes=[],
            )

            if subgraph.nodes:
                feedback = await detect_feedback(
                    response_text=assistant_msg.get("content", ""),
                    subgraph=subgraph,
                    user_id=user_id,
                )
                await apply_feedback(feedback, user_id)
                stats["feedback_applied"] = True

        except Exception:
            _log.warning(
                "process_graph.feedback_failed", user_id=user_id, exc_info=True
            )

    _log.info("process_graph.done", user_id=user_id, stats=stats)
    return stats
