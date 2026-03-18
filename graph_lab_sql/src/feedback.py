"""Post-response graph updates — track what was surfaced, completed, committed.

Uses invalidate_edge() for completions instead of setting strength to 0.
"""

import structlog
from graph_lab_sql.src import db
from graph_lab_sql.src.config import load_graph_config, resolve_model
from graph_lab_sql.src.llm import generate_json
from graph_lab_sql.src.types import ActiveSubgraph, FeedbackResult

logger = structlog.get_logger()


async def detect_feedback(
    response_text: str,
    subgraph: ActiveSubgraph,
    user_id: str,
) -> FeedbackResult:
    config = load_graph_config()
    model = resolve_model(config.ingest.quick_model, "LLM_MODEL_FAST")

    node_list = "\n".join(
        f"- {n.content} (id: {n.id})"
        for n in subgraph.nodes
        if n.content.lower() not in ("not done", "done", "surfaced")
    )

    prompt = f"""Analyze this assistant response in the context of the user's graph.

Assistant response:
{response_text}

Active graph nodes:
{node_list}

Identify:
1. surfaced_node_ids: which node IDs were mentioned or referenced in the response
2. completions_acknowledged: node IDs where the response acknowledges something is done
3. suppressions: node IDs for things deliberately NOT mentioned despite being in context

Return JSON:
{{
  "surfaced_node_ids": ["..."],
  "completions_acknowledged": ["..."],
  "suppressions": ["..."]
}}"""

    try:
        raw = await generate_json(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
        )
        return FeedbackResult(**raw)
    except Exception as e:
        logger.warning("feedback_detection_failed", error=str(e))
        return FeedbackResult()


async def apply_feedback(
    feedback: FeedbackResult,
    user_id: str,
) -> None:
    # Mark surfaced items
    if feedback.surfaced_node_ids:
        surfaced_node = await _ensure_status_node(user_id, "surfaced")
        for nid in feedback.surfaced_node_ids:
            await db.save_edge(
                user_id=user_id,
                from_node_id=nid,
                to_node_id=surfaced_node["id"],
            )

    # Mark completions — invalidate "not done" edges instead of zeroing strength
    if feedback.completions_acknowledged:
        done_node = await _ensure_status_node(user_id, "done")
        not_done_node = await db.find_node_by_content(user_id, "not done")
        for nid in feedback.completions_acknowledged:
            await db.save_edge(
                user_id=user_id,
                from_node_id=nid,
                to_node_id=done_node["id"],
            )
            # Invalidate the "not done" edge (bi-temporal: preserves history)
            if not_done_node:
                edges = await db.get_edges_from(nid, current_only=True)
                for edge in edges:
                    if edge["to_node_id"] == not_done_node["id"]:
                        await db.invalidate_edge(edge["id"])

    logger.info(
        "feedback_applied",
        user_id=user_id,
        surfaced=len(feedback.surfaced_node_ids),
        completed=len(feedback.completions_acknowledged),
    )


async def _ensure_status_node(user_id: str, status: str) -> dict:
    existing = await db.find_node_by_content(user_id, status)
    if existing:
        return existing
    return await db.save_node(user_id=user_id, content=status)
