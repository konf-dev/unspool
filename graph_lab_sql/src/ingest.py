"""Node extraction from user messages — with bi-temporal correction handling."""

import uuid
from datetime import datetime, timezone

import structlog
from graph_lab_sql.src import db
from graph_lab_sql.src.config import load_graph_config, load_prompt, resolve_model
from graph_lab_sql.src.embedding import generate_embeddings_batch
from graph_lab_sql.src.llm import generate_json
from graph_lab_sql.src.types import Correction, IngestOutput
from jinja2 import Template
from pydantic import ValidationError

logger = structlog.get_logger()


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


async def quick_ingest(
    user_id: str,
    message: str,
    stream_id: str,
) -> list[dict]:
    """Fast LLM call for node/edge extraction. Returns list of created/matched node dicts."""
    config = load_graph_config()
    model = resolve_model(config.ingest.quick_model, "LLM_MODEL_FAST")

    recent_nodes = await db.get_recent_nodes(
        user_id, limit=config.ingest.recent_nodes_context
    )
    existing_nodes_text = "\n".join(
        f"- {n['content']} (id: {n['id']})" for n in recent_nodes
    )

    template_text = load_prompt("ingest.md")
    template = Template(template_text)
    rendered = template.render(
        message=message,
        current_datetime=datetime.now(timezone.utc).isoformat(),
        existing_nodes=existing_nodes_text,
        max_nodes=config.ingest.quick_max_nodes,
    )

    try:
        raw = await generate_json(
            messages=[{"role": "user", "content": rendered}],
            model=model,
            temperature=0.3,
        )
        output = IngestOutput(**raw)
    except (ValidationError, Exception) as e:
        logger.warning("quick_ingest_failed", error=str(e), user_id=user_id)
        return []

    if len(output.nodes) > config.ingest.quick_max_nodes:
        output.nodes = output.nodes[: config.ingest.quick_max_nodes]

    # Create/match nodes
    content_to_id: dict[str, str] = {}
    created_nodes: list[dict] = []

    for ingest_node in output.nodes:
        if ingest_node.existing_match and _is_valid_uuid(ingest_node.existing_match):
            content_to_id[ingest_node.content] = ingest_node.existing_match
            await db.update_nodes_last_activated([ingest_node.existing_match])
            existing = await db.get_node(ingest_node.existing_match)
            if existing:
                created_nodes.append(existing)
            continue

        # LLM may return content string instead of UUID — fall back to content search
        existing = await db.find_node_by_content(user_id, ingest_node.content)
        if not existing and ingest_node.existing_match:
            # LLM gave a non-UUID match hint — try it as content
            existing = await db.find_node_by_content(
                user_id, ingest_node.existing_match
            )
        if existing:
            content_to_id[ingest_node.content] = existing["id"]
            await db.update_nodes_last_activated([existing["id"]])
            created_nodes.append(existing)
            continue

        node = await db.save_node(
            user_id=user_id,
            content=ingest_node.content,
            source_stream_id=stream_id,
        )
        content_to_id[ingest_node.content] = node["id"]
        created_nodes.append(node)

    # Create edges
    for edge in output.edges:
        from_id = content_to_id.get(edge.from_content)
        to_id = content_to_id.get(edge.to_content)
        if not from_id:
            from_id = await _resolve_content_to_id(
                user_id, edge.from_content, content_to_id
            )
        if not to_id:
            to_id = await _resolve_content_to_id(
                user_id, edge.to_content, content_to_id
            )
        if from_id and to_id:
            await db.save_edge(
                user_id=user_id,
                from_node_id=from_id,
                to_node_id=to_id,
                source_stream_id=stream_id,
            )

    # Apply edge updates
    for update in output.edge_updates:
        from_id = content_to_id.get(update.from_content)
        to_id = content_to_id.get(update.to_content)
        if not from_id:
            from_id = await _resolve_content_to_id(
                user_id, update.from_content, content_to_id
            )
        if not to_id:
            to_id = await _resolve_content_to_id(
                user_id, update.to_content, content_to_id
            )
        if from_id and to_id:
            await db.update_edge_strength(from_id, to_id, update.new_strength)

    # Process corrections (bi-temporal)
    corrections_applied = 0
    for correction in output.corrections:
        if correction.correction_type == "explicit":
            applied = await _apply_correction(
                user_id, correction, content_to_id, stream_id
            )
            if applied:
                corrections_applied += 1
        else:
            logger.info(
                "correction_detected_not_applied",
                type=correction.correction_type,
                target=correction.target_content,
            )

    logger.info(
        "quick_ingest_done",
        user_id=user_id,
        nodes_created=len(created_nodes),
        edges_created=len(output.edges),
        corrections_applied=corrections_applied,
    )
    return created_nodes


async def _apply_correction(
    user_id: str,
    correction: Correction,
    content_cache: dict[str, str],
    stream_id: str | None,
) -> bool:
    """Apply a bi-temporal correction: invalidate old edge, create new one.

    Uses content matching since existing graph data has untyped edges.
    """
    # Find target node
    target = await db.find_node_by_content(user_id, correction.target_content)
    if not target:
        logger.debug("correction_target_not_found", target=correction.target_content)
        return False

    target_id = target["id"]

    # Find edge from target to old_value by checking to_node content
    edges = await db.get_edges_from(target_id, current_only=True)
    old_edge_id = None
    for edge in edges:
        to_node = await db.get_node(edge["to_node_id"])
        if to_node and to_node["content"].lower() == correction.old_value.lower():
            old_edge_id = edge["id"]
            break

    if old_edge_id:
        await db.invalidate_edge(old_edge_id)
    else:
        logger.debug(
            "correction_old_edge_not_found",
            target=correction.target_content,
            old_value=correction.old_value,
        )

    # Find or create new_value node
    new_node = await db.find_node_by_content(user_id, correction.new_value)
    if not new_node:
        new_node = await db.save_node(
            user_id=user_id,
            content=correction.new_value,
            source_stream_id=stream_id,
        )
    content_cache[correction.new_value] = new_node["id"]

    # Create new edge
    await db.save_edge(
        user_id=user_id,
        from_node_id=target_id,
        to_node_id=new_node["id"],
        source_stream_id=stream_id,
    )

    logger.info(
        "correction_applied",
        target=correction.target_content,
        old_value=correction.old_value,
        new_value=correction.new_value,
        old_edge_invalidated=old_edge_id is not None,
    )
    return True


async def deep_ingest(user_id: str, stream_ids: list[str] | None = None) -> dict:
    """Async thorough extraction. Generates embeddings, discovers connections."""
    config = load_graph_config()
    stats = {"new_nodes": 0, "new_edges": 0, "embeddings": 0, "duplicates_merged": 0}

    all_nodes = await db.get_all_nodes(user_id)
    unembedded = [n for n in all_nodes if not n.get("embedding")]

    if unembedded:
        contents = [n["content"] for n in unembedded]
        embeddings = await generate_embeddings_batch(contents)
        for node, emb in zip(unembedded, embeddings):
            await db.update_node_embedding(node["id"], emb)
            stats["embeddings"] += 1

    all_nodes = await db.get_all_nodes(user_id)
    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = config.evolution.dedup_threshold

    for node_a in nodes_with_emb:
        similar = await db.search_nodes_semantic(
            user_id,
            node_a["embedding"],
            limit=5,
            min_similarity=threshold,
        )
        for match in similar:
            if match["id"] == node_a["id"]:
                continue
            if match.get("created_at", "") < node_a.get("created_at", ""):
                keep, remove = match, node_a
            else:
                keep, remove = node_a, match
            await db.redirect_edges(remove["id"], keep["id"])
            await db.delete_node(remove["id"])
            stats["duplicates_merged"] += 1
            break

    logger.info("deep_ingest_done", user_id=user_id, stats=stats)
    return stats


async def _resolve_content_to_id(
    user_id: str, content: str, cache: dict[str, str]
) -> str | None:
    if content in cache:
        return cache[content]
    node = await db.find_node_by_content(user_id, content)
    if node:
        cache[content] = node["id"]
        return node["id"]
    if content.lower() in ("not done", "done", "surfaced"):
        new_node = await db.save_node(user_id=user_id, content=content.lower())
        cache[content] = new_node["id"]
        return new_node["id"]
    return None
