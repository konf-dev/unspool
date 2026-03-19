"""Unified post-processing job: embeddings + graph ingest + feedback.

Replaces the separate process_conversation and process_graph jobs.
Triggered by agent state flags: ingest (graph) and/or embeddings (items).
"""

from typing import Any

from src.db import supabase as db
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.process_message")


@observe("job.process_message")
async def run_process_message(
    user_id: str,
    message_ids: list[str],
    tool_calls: list[dict[str, Any]] | None = None,
    ingest: bool = False,
    embeddings: bool = False,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "embedded": 0,
        "nodes_created": 0,
        "feedback_applied": False,
    }

    messages = await db.get_messages_by_ids(user_id, message_ids)
    user_msg = next((m for m in messages if m.get("role") == "user"), None)
    assistant_msg = next((m for m in messages if m.get("role") == "assistant"), None)

    # Phase 1: Generate embeddings for items without them
    if embeddings:
        stats["embedded"] = await _generate_item_embeddings(user_id)

    # Phase 2: Graph ingest + feedback
    if ingest and user_msg:
        ingest_stats = await _ingest_and_feedback(user_id, user_msg, assistant_msg)
        stats.update(ingest_stats)

    _log.info("process_message.done", user_id=user_id, stats=stats)
    return stats


async def _generate_item_embeddings(user_id: str) -> int:
    count = 0
    try:
        from src.llm.registry import get_embedding_provider

        embedder = get_embedding_provider()
        items = await db.get_items_without_embeddings(user_id)
        for item in items:
            try:
                text = (
                    f"{item.get('interpreted_action', '')} {item.get('raw_text', '')}"
                )
                embedding = await embedder.embed(text)
                await db.update_item_embedding(str(item["id"]), user_id, embedding)
                count += 1
            except Exception:
                _log.warning(
                    "process_message.embed_item_failed",
                    item_id=str(item.get("id", "unknown")),
                    exc_info=True,
                )
    except Exception:
        _log.warning("process_message.embedding_phase_failed", exc_info=True)
    return count


async def _ingest_and_feedback(
    user_id: str,
    user_msg: dict[str, Any],
    assistant_msg: dict[str, Any] | None,
) -> dict[str, Any]:
    stats: dict[str, Any] = {"nodes_created": 0, "feedback_applied": False}

    try:
        from src.graph.feedback import apply_feedback, detect_feedback
        from src.graph.ingest import quick_ingest
        from src.graph.retrieval import build_active_subgraph
    except ImportError:
        _log.warning("process_message.graph_modules_not_available")
        return stats

    # Ingest user message into graph
    try:
        user_content = user_msg.get("content", "")
        user_msg_id = str(user_msg["id"])
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
    except Exception:
        _log.warning("process_message.ingest_failed", user_id=user_id, exc_info=True)

    # Embed new graph nodes
    try:
        from src.graph import db as graph_db
        from src.llm.embedding import OpenAIEmbedding

        all_nodes = await graph_db.get_all_nodes(user_id)
        unembedded = [n for n in all_nodes if not n.get("embedding")]
        if unembedded:
            embedder = OpenAIEmbedding()
            contents = [n["content"] for n in unembedded]
            node_embeddings = await embedder.embed_batch(contents)
            for node, emb in zip(unembedded, node_embeddings):
                await graph_db.update_node_embedding(node["id"], emb)
    except Exception:
        _log.warning(
            "process_message.node_embedding_failed", user_id=user_id, exc_info=True
        )

    # Feedback from assistant response
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
                "process_message.feedback_failed", user_id=user_id, exc_info=True
            )

    return stats
