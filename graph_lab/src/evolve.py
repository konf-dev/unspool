"""Async graph evolution — deep ingest, connection discovery, decay, reconciliation."""

import structlog
from graph_lab.src import db
from graph_lab.src.config import load_graph_config, load_prompt, resolve_model
from graph_lab.src.embedding import generate_embeddings_batch
from graph_lab.src.llm import generate_json
from graph_lab.src.types import EvolutionOutput, EvolutionResult
from jinja2 import Template

logger = structlog.get_logger()


async def evolve_graph(user_id: str) -> EvolutionResult:
    """
    Run full graph evolution cycle:
    1. Generate missing embeddings
    2. Discover new connections via similarity
    3. LLM-based synthesis (merges, contradictions)
    4. Edge decay and pruning
    """
    config = load_graph_config()
    result = EvolutionResult()

    # Step 1: Generate embeddings for unembedded nodes
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
        # Refresh nodes with embeddings
        all_nodes = await db.get_all_nodes(user_id)

    # Step 2: Discover connections via embedding similarity
    nodes_with_emb = [n for n in all_nodes if n.get("embedding")]
    threshold = config.evolution.similarity_threshold

    for node in nodes_with_emb:
        similar = await db.search_nodes_semantic(
            user_id, node["embedding"], limit=5, min_similarity=threshold
        )
        for match in similar:
            if match["id"] == node["id"]:
                continue
            # Check if edge already exists
            existing_edges = await db.get_edges_from(node["id"])
            already_connected = any(e.get("out") == match["id"] for e in existing_edges)
            if not already_connected:
                await db.save_edge(
                    user_id=user_id,
                    from_node_id=node["id"],
                    to_node_id=match["id"],
                )
                result.edges_created += 1

    # Step 3: LLM-based synthesis
    if len(all_nodes) > 5:
        try:
            synthesis = await _llm_synthesis(user_id, all_nodes, config)
            await _apply_synthesis(user_id, synthesis, result)
        except Exception as e:
            logger.warning("synthesis_failed", error=str(e))

    # Step 4: Edge decay
    decayed = await db.decay_edges(
        user_id,
        config.evolution.edge_decay_factor,
        config.evolution.edge_decay_min,
    )
    result.edges_decayed = decayed

    # Step 5: Prune weak edges
    pruned = await db.prune_weak_edges(user_id, config.evolution.edge_decay_min)
    result.edges_pruned = pruned

    logger.info("evolution_complete", user_id=user_id, result=result.model_dump())
    return result


async def _llm_synthesis(user_id: str, nodes: list[dict], config) -> EvolutionOutput:
    """LLM-based graph analysis: find merges, contradictions, new edges."""
    model = resolve_model(config.ingest.deep_model, "LLM_MODEL")

    # Load edges for context
    node_ids = [n["id"] for n in nodes]
    edges = await db.get_edges_between(node_ids)

    # Render evolve prompt
    template_text = load_prompt("evolve.md")
    template = Template(template_text)
    rendered = template.render(
        nodes="\n".join(f"- {n['content']} (id: {n['id']})" for n in nodes),
        edges="\n".join(
            f"- {e.get('in', '?')} -> {e.get('out', '?')} (strength: {e.get('strength', 1.0):.2f})"
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
    """Apply LLM synthesis suggestions to the graph."""
    # Apply merges
    for merge in synthesis.merges:
        try:
            await db.redirect_edges(merge.remove_node_id, merge.keep_node_id)
            await db.delete_node(merge.remove_node_id)
            result.nodes_merged += 1
        except Exception as e:
            logger.warning("merge_failed", error=str(e), merge=merge.model_dump())

    # Apply new edges
    for edge in synthesis.new_edges:
        try:
            await db.save_edge(
                user_id=user_id,
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
            )
            result.edges_created += 1
        except Exception as e:
            logger.warning("edge_create_failed", error=str(e))

    # Log contradictions (don't auto-resolve, just flag)
    for contradiction in synthesis.contradictions:
        logger.info(
            "contradiction_found",
            user_id=user_id,
            node_a=contradiction.node_id_a,
            node_b=contradiction.node_id_b,
            description=contradiction.description,
        )
        result.contradictions_found += 1

    # Apply refinements
    for refinement in synthesis.refinements:
        try:
            await db.update_node_content(refinement.node_id, refinement.new_content)
        except Exception as e:
            logger.warning("refinement_failed", error=str(e))
