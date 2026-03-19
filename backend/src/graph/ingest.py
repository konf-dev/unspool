"""Node extraction from user messages — with pre-filter and bi-temporal corrections."""

import json
import re
import uuid
from datetime import datetime, timezone

from src.graph import db
from src.llm.embedding import OpenAIEmbedding
from src.llm.registry import get_llm_provider
from src.config_loader import load_config
from src.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger
from src.graph.types import Correction, IngestOutput

_log = get_logger("graph.ingest")


def should_ingest(message: str) -> tuple[bool, str]:
    """Quick pre-filter. Returns (should_ingest, skip_reason)."""
    stripped = message.strip()

    if len(stripped) < 3:
        return False, "too_short"

    if not any(c.isalnum() for c in stripped):
        return False, "no_alphanumeric"

    if all(c in ".,!?;:…-—–_ \t\n" for c in stripped):
        return False, "punctuation_only"

    return True, ""


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


async def quick_ingest(
    user_id: str,
    message: str,
    message_id: str,
    message_timestamp: str | None = None,
) -> list[dict]:
    """Fast LLM call for node/edge extraction. Returns created/matched node dicts."""
    ok, reason = should_ingest(message)
    if not ok:
        _log.info("graph.ingest.skipped", user_id=user_id, reason=reason)
        return []

    graph_config = load_config("graph")
    ingest_cfg = graph_config.get("ingest", {})
    model = ingest_cfg.get("quick_model")
    max_nodes = ingest_cfg.get("quick_max_nodes", 10)
    recent_limit = ingest_cfg.get("recent_nodes_context", 30)

    recent_nodes = await db.get_recent_nodes(user_id, limit=recent_limit)
    existing_nodes_text = "\n".join(
        f"- {n['content']} (id: {n['id']})" for n in recent_nodes
    )

    current_dt = message_timestamp or datetime.now(timezone.utc).isoformat()

    rendered = render_prompt(
        "graph_ingest.md",
        {
            "message": message,
            "current_datetime": current_dt,
            "existing_nodes": existing_nodes_text,
            "max_nodes": max_nodes,
        },
    )

    provider = get_llm_provider()
    try:
        result = await provider.generate(
            [
                {"role": "system", "content": rendered},
                {"role": "user", "content": message},
            ],
            model=model,
        )
        raw_json = _extract_json(result.content)
        output = IngestOutput(**raw_json)
    except Exception as e:
        _log.warning("graph.ingest.failed", error=str(e), user_id=user_id)
        return []

    if len(output.nodes) > max_nodes:
        output.nodes = output.nodes[:max_nodes]

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

        existing = await db.find_node_by_content(user_id, ingest_node.content)
        if not existing and ingest_node.existing_match:
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
            source_message_id=message_id,
        )
        content_to_id[ingest_node.content] = node["id"]
        created_nodes.append(node)

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
                source_message_id=message_id,
            )

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

    corrections_applied = 0
    for correction in output.corrections:
        if correction.correction_type == "explicit":
            applied = await _apply_correction(
                user_id, correction, content_to_id, message_id
            )
            if applied:
                corrections_applied += 1

    _log.info(
        "graph.ingest.done",
        user_id=user_id,
        nodes_created=len(created_nodes),
        edges_created=len(output.edges),
        corrections_applied=corrections_applied,
    )
    return created_nodes


async def deep_ingest(user_id: str) -> dict:
    """Generate embeddings and deduplicate near-duplicate nodes."""
    graph_config = load_config("graph")
    evolution_cfg = graph_config.get("evolution", {})
    stats = {"new_nodes": 0, "new_edges": 0, "embeddings": 0, "duplicates_merged": 0}

    embedder = OpenAIEmbedding(model=evolution_cfg.get("embedding_model"))
    all_nodes = await db.get_all_nodes(user_id)
    unembedded = [n for n in all_nodes if not n.get("embedding")]

    if unembedded:
        contents = [n["content"] for n in unembedded]
        embeddings = await embedder.embed_batch(contents)
        for node, emb in zip(unembedded, embeddings):
            await db.update_node_embedding(node["id"], emb)
            stats["embeddings"] += 1

    all_nodes = await db.get_all_nodes(user_id)
    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = evolution_cfg.get("dedup_threshold", 0.9)

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

    _log.info("graph.deep_ingest.done", user_id=user_id, stats=stats)
    return stats


async def _apply_correction(
    user_id: str,
    correction: Correction,
    content_cache: dict[str, str],
    message_id: str | None,
) -> bool:
    target = await db.find_node_by_content(user_id, correction.target_content)
    if not target:
        return False

    target_id = target["id"]

    edges = await db.get_edges_from(target_id, current_only=True)
    old_edge_id = None
    for edge in edges:
        to_node = await db.get_node(edge["to_node_id"])
        if to_node and to_node["content"].lower() == correction.old_value.lower():
            old_edge_id = edge["id"]
            break

    if old_edge_id:
        await db.invalidate_edge(old_edge_id)

    new_node = await db.find_node_by_content(user_id, correction.new_value)
    if not new_node:
        new_node = await db.save_node(
            user_id=user_id,
            content=correction.new_value,
            source_message_id=message_id,
        )
    content_cache[correction.new_value] = new_node["id"]

    await db.save_edge(
        user_id=user_id,
        from_node_id=target_id,
        to_node_id=new_node["id"],
        source_message_id=message_id,
    )

    _log.info(
        "graph.correction_applied",
        target=correction.target_content,
        old_edge_invalidated=old_edge_id is not None,
    )
    return True


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


def _extract_json(content: str) -> dict:
    raw = content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    for i, ch in enumerate(raw):
        if ch in "{[":
            try:
                return json.loads(raw[i:])
            except json.JSONDecodeError:
                break

    return {"nodes": [], "edges": [], "edge_updates": [], "corrections": []}
