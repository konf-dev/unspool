"""Node extraction from user messages."""

from datetime import datetime, timezone

import structlog
from graph_lab.src import db
from graph_lab.src.config import load_graph_config, load_prompt, resolve_model
from graph_lab.src.embedding import generate_embeddings_batch
from graph_lab.src.llm import generate_json
from graph_lab.src.types import IngestOutput
from jinja2 import Template
from pydantic import ValidationError

logger = structlog.get_logger()


async def quick_ingest(
    user_id: str,
    message: str,
    stream_id: str,
) -> list[dict]:
    """
    Sync node extraction. Fast LLM call.
    Returns list of created/matched node dicts.
    """
    config = load_graph_config()
    model = resolve_model(config.ingest.quick_model, "LLM_MODEL_FAST")

    # Load recent nodes for deduplication
    recent_nodes = await db.get_recent_nodes(user_id, limit=config.ingest.recent_nodes_context)
    existing_nodes_text = "\n".join(f"- {n['content']} (id: {n['id']})" for n in recent_nodes)

    # Render prompt
    template_text = load_prompt("ingest.md")
    template = Template(template_text)
    rendered = template.render(
        message=message,
        current_datetime=datetime.now(timezone.utc).isoformat(),
        existing_nodes=existing_nodes_text,
        max_nodes=config.ingest.quick_max_nodes,
    )

    # LLM call
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

    # Enforce cap
    if len(output.nodes) > config.ingest.quick_max_nodes:
        output.nodes = output.nodes[: config.ingest.quick_max_nodes]

    # Create/match nodes
    content_to_id: dict[str, str] = {}
    created_nodes: list[dict] = []

    for ingest_node in output.nodes:
        if ingest_node.existing_match:
            # LLM matched to an existing node
            content_to_id[ingest_node.content] = ingest_node.existing_match
            # Update last_activated
            await db.update_nodes_last_activated([ingest_node.existing_match])
            existing = await db.get_node(ingest_node.existing_match)
            if existing:
                created_nodes.append(existing)
            continue

        # Check for exact match the LLM might have missed
        existing = await db.find_node_by_content(user_id, ingest_node.content)
        if existing:
            content_to_id[ingest_node.content] = existing["id"]
            await db.update_nodes_last_activated([existing["id"]])
            created_nodes.append(existing)
            continue

        # Create new node
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
        # If the edge references a content string not in our map, try to find it
        if not from_id:
            from_id = await _resolve_content_to_id(user_id, edge.from_content, content_to_id)
        if not to_id:
            to_id = await _resolve_content_to_id(user_id, edge.to_content, content_to_id)
        if from_id and to_id:
            await db.save_edge(
                user_id=user_id,
                from_node_id=from_id,
                to_node_id=to_id,
                source_stream_id=stream_id,
            )

    # Apply edge updates (e.g., setting "not done" edges to strength 0)
    for update in output.edge_updates:
        from_id = content_to_id.get(update.from_content)
        to_id = content_to_id.get(update.to_content)
        if not from_id:
            from_id = await _resolve_content_to_id(user_id, update.from_content, content_to_id)
        if not to_id:
            to_id = await _resolve_content_to_id(user_id, update.to_content, content_to_id)
        if from_id and to_id:
            await db.update_edge_strength(from_id, to_id, update.new_strength)

    logger.info(
        "quick_ingest_done",
        user_id=user_id,
        nodes_created=len(created_nodes),
        edges_created=len(output.edges),
    )
    return created_nodes


async def deep_ingest(user_id: str, stream_ids: list[str] | None = None) -> dict:
    """
    Async thorough extraction. Runs post-response.
    Generates embeddings, discovers connections via similarity.
    """
    config = load_graph_config()
    stats = {"new_nodes": 0, "new_edges": 0, "embeddings": 0, "duplicates_merged": 0}

    # Generate embeddings for all unembedded nodes
    all_nodes = await db.get_all_nodes(user_id)
    unembedded = [n for n in all_nodes if not n.get("embedding")]

    if unembedded:
        contents = [n["content"] for n in unembedded]
        embeddings = await generate_embeddings_batch(contents)
        for node, emb in zip(unembedded, embeddings):
            await db.update_node_embedding(node["id"], emb)
            stats["embeddings"] += 1

    # Discover connections via embedding similarity
    all_nodes = await db.get_all_nodes(user_id)
    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = config.evolution.dedup_threshold

    for i, node_a in enumerate(nodes_with_emb):
        similar = await db.search_nodes_semantic(
            user_id,
            node_a["embedding"],
            limit=5,
            min_similarity=threshold,
        )
        for match in similar:
            if match["id"] == node_a["id"]:
                continue
            # Potential duplicate — merge (keep older node)
            if match.get("created_at", "") < node_a.get("created_at", ""):
                keep, remove = match, node_a
            else:
                keep, remove = node_a, match
            await db.redirect_edges(remove["id"], keep["id"])
            await db.delete_node(remove["id"])
            stats["duplicates_merged"] += 1
            break  # only merge one per pass

    logger.info("deep_ingest_done", user_id=user_id, stats=stats)
    return stats


async def _resolve_content_to_id(user_id: str, content: str, cache: dict[str, str]) -> str | None:
    """Try to find a node ID for a content string."""
    if content in cache:
        return cache[content]
    # Check DB for existing node with this content
    node = await db.find_node_by_content(user_id, content)
    if node:
        cache[content] = node["id"]
        return node["id"]
    # Create a status/meta node if it's a known status
    if content.lower() in ("not done", "done", "surfaced"):
        new_node = await db.save_node(user_id=user_id, content=content.lower())
        cache[content] = new_node["id"]
        return new_node["id"]
    return None
