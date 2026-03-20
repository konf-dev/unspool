"""Post-response graph updates — track surfaced, completed, committed."""

import json
import re

from src.graph import db
from src.graph.types import ActiveSubgraph, FeedbackResult
from src.llm.registry import get_llm_provider
from src.config_loader import load_config
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe, update_current_observation
from src.telemetry.logger import get_logger

_log = get_logger("graph.feedback")


@observe("graph.feedback")
async def detect_feedback(
    response_text: str,
    subgraph: ActiveSubgraph,
    user_id: str,
) -> FeedbackResult:
    graph_config = load_config("graph")
    ingest_cfg = graph_config.get("ingest", {})
    model = ingest_cfg.get("quick_model")

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

    llm_messages = [{"role": "user", "content": prompt}]
    provider = get_llm_provider()
    try:
        result = await provider.generate(
            llm_messages,
            model=model,
        )
        update_current_observation(
            model=model,
            input=llm_messages,
            output=result.content,
            usage={
                "input": result.input_tokens,
                "output": result.output_tokens,
            },
        )
        raw = result.content.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
            if fence:
                data = json.loads(fence.group(1).strip())
            else:
                return FeedbackResult()
        return FeedbackResult(**data)
    except Exception as e:
        report_error("graph.feedback_detection_failed", e, user_id=user_id)
        return FeedbackResult()


async def apply_feedback(
    feedback: FeedbackResult,
    user_id: str,
) -> None:
    if feedback.surfaced_node_ids:
        surfaced_node = await _ensure_status_node(user_id, "surfaced")
        for nid in feedback.surfaced_node_ids:
            await db.save_edge(
                user_id=user_id,
                from_node_id=nid,
                to_node_id=surfaced_node["id"],
            )

    if feedback.completions_acknowledged:
        done_node = await _ensure_status_node(user_id, "done")
        not_done_node = await db.find_node_by_content(user_id, "not done")
        for nid in feedback.completions_acknowledged:
            await db.save_edge(
                user_id=user_id,
                from_node_id=nid,
                to_node_id=done_node["id"],
            )
            if not_done_node:
                edges = await db.get_edges_from(nid, current_only=True)
                for edge in edges:
                    if edge["to_node_id"] == not_done_node["id"]:
                        await db.invalidate_edge(edge["id"])

    _log.info(
        "graph.feedback.done",
        user_id=user_id,
        surfaced_count=len(feedback.surfaced_node_ids),
        completed_count=len(feedback.completions_acknowledged),
    )


async def _ensure_status_node(user_id: str, status: str) -> dict:
    existing = await db.find_node_by_content(user_id, status)
    if existing:
        return existing
    return await db.save_node(user_id=user_id, content=status)
