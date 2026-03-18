"""Temporal-aware graph evolution — invalidates instead of deletes."""

import uuid

import structlog
from graph_lab_sql.src import db
from graph_lab_sql.src.config import load_graph_config, load_prompt, resolve_model
from graph_lab_sql.src.embedding import generate_embeddings_batch
from graph_lab_sql.src.llm import generate_json
from graph_lab_sql.src.types import EvolutionOutput, EvolutionResult
from jinja2 import Template


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


logger = structlog.get_logger()


async def evolve_graph(user_id: str) -> EvolutionResult:
    """
    Temporal-aware evolution cycle:
    1. Generate missing embeddings
    2. Discover new connections via similarity
    3. LLM-based synthesis (merges, contradictions)
    4. Edge decay (skips decay_exempt)
    5. Prune weak edges (invalidate, not delete)
    6. Rebuild neighbor cache
    """
    config = load_graph_config()
    result = EvolutionResult()

    # Step 1: Generate embeddings
    all_nodes = await db.get_all_nodes(user_id)
    unembedded = [n for n in all_nodes if not n.get("embedding")]

    if unembedded:
        contents = [n["content"] for n in unembedded]
        embeddings = await generate_embeddings_batch(
            contents, model=config.evolution.embedding_model
        )
        for node, emb in zip(unembedded, embeddings):
            await db.update_node_embedding(node["id"], emb)
            result.embeddings_generated += 1
        all_nodes = await db.get_all_nodes(user_id)

    # Step 2: Discover connections
    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = config.evolution.similarity_threshold

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

    # Step 3: LLM synthesis
    if len(all_nodes) > 5:
        try:
            synthesis = await _llm_synthesis(user_id, all_nodes, config)
            await _apply_synthesis(user_id, synthesis, result)
        except Exception as e:
            logger.warning("synthesis_failed", error=str(e))

    # Step 4: Decay (skips decay_exempt edges)
    decayed = await db.decay_edges(
        user_id,
        config.evolution.edge_decay_factor,
        config.evolution.edge_decay_min,
    )
    result.edges_decayed = decayed

    # Step 5: Prune weak edges (invalidates, not deletes)
    pruned = await db.prune_weak_edges(user_id, config.evolution.edge_decay_min)
    result.edges_pruned = pruned

    # Step 6: Full neighbor cache rebuild
    await db.rebuild_neighbor_cache(user_id)

    logger.info("evolution_complete", user_id=user_id, result=result.model_dump())
    return result


async def _llm_synthesis(user_id: str, nodes: list[dict], config) -> EvolutionOutput:
    model = resolve_model(config.ingest.deep_model, "LLM_MODEL")

    node_ids = [n["id"] for n in nodes]
    edges = await db.get_edges_between(node_ids)

    id_to_content = {n["id"]: n["content"] for n in nodes}

    template_text = load_prompt("evolve.md")
    template = Template(template_text)
    rendered = template.render(
        nodes="\n".join(f"- {n['content']} (id: {n['id']})" for n in nodes),
        edges="\n".join(
            f"- {id_to_content.get(e.get('from_node_id'), '?')} -> "
            f"{id_to_content.get(e.get('to_node_id'), '?')} "
            f"(strength: {e.get('strength', 1.0):.2f})"
            for e in edges
        ),
        user_id=user_id,
    )

    raw = await generate_json(
        messages=[{"role": "user", "content": rendered}],
        model=model,
        temperature=0.3,
    )
    return EvolutionOutput(**raw)


async def _apply_synthesis(
    user_id: str, synthesis: EvolutionOutput, result: EvolutionResult
) -> None:
    for merge in synthesis.merges:
        if not (
            _is_valid_uuid(merge.keep_node_id) and _is_valid_uuid(merge.remove_node_id)
        ):
            logger.debug("merge_skipped_invalid_ids", merge=merge.model_dump())
            continue
        try:
            await db.redirect_edges(merge.remove_node_id, merge.keep_node_id)
            await db.update_node_status(merge.remove_node_id, "merged")
            result.nodes_merged += 1
        except Exception as e:
            logger.warning("merge_failed", error=str(e), merge=merge.model_dump())

    for edge in synthesis.new_edges:
        if not (_is_valid_uuid(edge.from_node_id) and _is_valid_uuid(edge.to_node_id)):
            logger.debug(
                "edge_skipped_invalid_ids",
                from_id=edge.from_node_id,
                to_id=edge.to_node_id,
            )
            continue
        try:
            await db.save_edge(
                user_id=user_id,
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
            )
            result.edges_created += 1
        except Exception as e:
            logger.warning("edge_create_failed", error=str(e))

    for contradiction in synthesis.contradictions:
        logger.info(
            "contradiction_found",
            user_id=user_id,
            node_a=contradiction.node_id_a,
            node_b=contradiction.node_id_b,
            description=contradiction.description,
        )
        result.contradictions_found += 1

    for refinement in synthesis.refinements:
        if not _is_valid_uuid(refinement.node_id):
            logger.debug("refinement_skipped_invalid_id", node_id=refinement.node_id)
            continue
        try:
            await db.update_node_content(refinement.node_id, refinement.new_content)
        except Exception as e:
            logger.warning("refinement_failed", error=str(e))
