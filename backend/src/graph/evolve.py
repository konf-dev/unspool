"""Temporal-aware graph evolution — invalidates instead of deletes."""

import json
import re
import uuid

from src.graph import db
from src.graph.types import EvolutionOutput, EvolutionResult
from src.llm.embedding import OpenAIEmbedding
from src.llm.registry import get_llm_provider
from src.config_loader import load_config
from src.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger

_log = get_logger("graph.evolve")


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


async def evolve_graph(user_id: str) -> EvolutionResult:
    """
    Evolution cycle:
    1. Generate missing embeddings
    2. Discover new connections via similarity
    3. LLM-based synthesis (merges, contradictions)
    4. Edge decay (skips decay_exempt)
    5. Prune weak edges (invalidate, not delete)
    6. Rebuild neighbor cache
    """
    graph_config = load_config("graph")
    evolution_cfg = graph_config.get("evolution", {})
    ingest_cfg = graph_config.get("ingest", {})
    result = EvolutionResult()

    embedder = OpenAIEmbedding(model=evolution_cfg.get("embedding_model"))

    all_nodes = await db.get_all_nodes(user_id)
    unembedded = [n for n in all_nodes if not n.get("embedding")]

    if unembedded:
        contents = [n["content"] for n in unembedded]
        embeddings = await embedder.embed_batch(contents)
        for node, emb in zip(unembedded, embeddings):
            await db.update_node_embedding(node["id"], emb)
            result.embeddings_generated += 1
        all_nodes = await db.get_all_nodes(user_id)

    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = evolution_cfg.get("similarity_threshold", 0.8)

    for node in nodes_with_emb:
        similar = await db.search_nodes_semantic(
            user_id, node["embedding"], limit=5, min_similarity=threshold
        )
        for match in similar:
            if match["id"] == node["id"]:
                continue
            existing_edges = await db.get_edges_from(node["id"])
            already_connected = any(
                e.get("to_node_id") == match["id"] for e in existing_edges
            )
            if not already_connected:
                await db.save_edge(
                    user_id=user_id,
                    from_node_id=node["id"],
                    to_node_id=match["id"],
                )
                result.edges_created += 1

    if len(all_nodes) > 5:
        try:
            synthesis = await _llm_synthesis(user_id, all_nodes, ingest_cfg)
            await _apply_synthesis(user_id, synthesis, result)
        except Exception as e:
            _log.warning("graph.synthesis_failed", error=str(e))

    decayed = await db.decay_edges(
        user_id,
        evolution_cfg.get("edge_decay_factor", 0.99),
        evolution_cfg.get("edge_decay_min", 0.01),
    )
    result.edges_decayed = decayed

    pruned = await db.prune_weak_edges(
        user_id, evolution_cfg.get("edge_decay_min", 0.01)
    )
    result.edges_pruned = pruned

    await db.rebuild_neighbor_cache(user_id)

    _log.info("graph.evolution.done", user_id=user_id, result=result.model_dump())
    return result


async def _llm_synthesis(
    user_id: str, nodes: list[dict], ingest_cfg: dict
) -> EvolutionOutput:
    model = ingest_cfg.get("deep_model")

    node_ids = [n["id"] for n in nodes]
    edges = await db.get_edges_between(node_ids)

    id_to_content = {n["id"]: n["content"] for n in nodes}

    rendered = render_prompt(
        "graph_evolve.md",
        {
            "nodes": "\n".join(f"- {n['content']} (id: {n['id']})" for n in nodes),
            "edges": "\n".join(
                f"- {id_to_content.get(e.get('from_node_id'), '?')} -> "
                f"{id_to_content.get(e.get('to_node_id'), '?')} "
                f"(strength: {e.get('strength', 1.0):.2f})"
                for e in edges
            ),
            "user_id": user_id,
        },
    )

    provider = get_llm_provider()
    result = await provider.generate(
        [{"role": "user", "content": rendered}],
        model=model,
    )

    raw = result.content.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        if fence:
            data = json.loads(fence.group(1).strip())
        else:
            data = {
                "merges": [],
                "new_edges": [],
                "contradictions": [],
                "refinements": [],
            }

    return EvolutionOutput(**data)


async def _apply_synthesis(
    user_id: str, synthesis: EvolutionOutput, result: EvolutionResult
) -> None:
    for merge in synthesis.merges:
        if not (
            _is_valid_uuid(merge.keep_node_id) and _is_valid_uuid(merge.remove_node_id)
        ):
            continue
        try:
            await db.redirect_edges(merge.remove_node_id, merge.keep_node_id)
            await db.update_node_status(merge.remove_node_id, "merged")
            result.nodes_merged += 1
        except Exception as e:
            _log.warning("graph.merge_failed", error=str(e))

    for edge in synthesis.new_edges:
        if not (_is_valid_uuid(edge.from_node_id) and _is_valid_uuid(edge.to_node_id)):
            continue
        try:
            await db.save_edge(
                user_id=user_id,
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
            )
            result.edges_created += 1
        except Exception as e:
            _log.warning("graph.edge_create_failed", error=str(e))

    result.contradictions_found += len(synthesis.contradictions)

    for refinement in synthesis.refinements:
        if not _is_valid_uuid(refinement.node_id):
            continue
        try:
            await db.update_node_content(refinement.node_id, refinement.new_content)
        except Exception as e:
            _log.warning("graph.refinement_failed", error=str(e))
