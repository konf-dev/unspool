"""Trigger chain orchestration — builds the active subgraph for reasoning."""

import asyncio

import structlog
from graph_lab.src import db
from graph_lab.src.config import load_graph_config, load_triggers_config
from graph_lab.src.triggers import get_trigger
from graph_lab.src.types import ActiveSubgraph, Edge, Node, TriggerResult

logger = structlog.get_logger()


async def build_active_subgraph(
    user_id: str,
    message: str,
    message_embedding: list[float] | None,
    quick_nodes: list[dict],
) -> ActiveSubgraph:
    """
    Run configured trigger chain, assemble active subgraph.
    """
    config = load_graph_config()
    trigger_config = load_triggers_config()

    context = {
        "message": message,
        "message_embedding": message_embedding,
        "quick_node_ids": [n["id"] for n in quick_nodes],
        "collected_node_ids": set(n["id"] for n in quick_nodes),
    }

    # Group triggers: independent (no depends_on) vs dependent
    independent: list[tuple[str, dict]] = []
    dependent: list[tuple[str, dict]] = []

    for name, tdef in trigger_config.triggers.items():
        if not tdef.enabled:
            continue
        if tdef.depends_on:
            dependent.append((name, tdef))
        else:
            independent.append((name, tdef))

    trigger_results: list[TriggerResult] = []

    # Phase 1: Run independent triggers in parallel
    if independent:
        tasks = [_run_trigger(name, user_id, context, tdef) for name, tdef in independent]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("trigger_failed", error=str(result))
                continue
            trigger_results.append(result)
            context["collected_node_ids"].update(result.node_ids)

    # Phase 2: Run dependent triggers sequentially
    for name, tdef in dependent:
        try:
            result = await _run_trigger(name, user_id, context, tdef)
            trigger_results.append(result)
            context["collected_node_ids"].update(result.node_ids)
        except Exception as e:
            logger.warning("trigger_failed", trigger=name, error=str(e))

    # Phase 3: Load full subgraph (nodes + edges between them)
    all_ids = list(context["collected_node_ids"])
    max_nodes = config.retrieval.max_subgraph_nodes

    if len(all_ids) > max_nodes:
        all_ids = _prioritize_nodes(all_ids, quick_nodes, trigger_results, max_nodes)

    nodes_raw = await db.get_nodes_by_ids(all_ids)
    edges_raw = await db.get_edges_between(all_ids)

    # Update activation timestamps
    await db.update_nodes_last_activated(all_ids)

    nodes = [Node(**n) for n in nodes_raw if _is_valid_node(n)]
    edges = [Edge(**_map_edge(e)) for e in edges_raw if _is_valid_edge(e)]

    logger.info(
        "subgraph_built",
        user_id=user_id,
        total_nodes=len(nodes),
        total_edges=len(edges),
        triggers_fired=len(trigger_results),
    )

    return ActiveSubgraph(
        nodes=nodes,
        edges=edges,
        trigger_results=trigger_results,
    )


async def _run_trigger(name: str, user_id: str, context: dict, tdef) -> TriggerResult:
    trigger_fn = get_trigger(tdef.type)
    if not trigger_fn:
        logger.warning("trigger_not_found", name=name, type=tdef.type)
        return TriggerResult(trigger_name=name)
    return await trigger_fn(user_id, context, tdef.params)


def _prioritize_nodes(
    all_ids: list[str],
    quick_nodes: list[dict],
    trigger_results: list[TriggerResult],
    max_nodes: int,
) -> list[str]:
    """
    Prioritize nodes when subgraph exceeds max size.
    Priority: quick_ingest nodes > specific triggers > broad triggers.
    """
    priority: dict[str, int] = {}

    # Quick ingest nodes get highest priority
    for n in quick_nodes:
        priority[n["id"]] = 100

    # Specific triggers (temporal, open_items, suppression) > broad (semantic, recent, walk)
    specific = {"temporal", "status_not_done", "status_surfaced"}
    for tr in trigger_results:
        is_specific = any(s in tr.trigger_name for s in specific)
        score = 50 if is_specific else 10
        for nid in tr.node_ids:
            priority[nid] = max(priority.get(nid, 0), score)

    # Sort by priority descending, take top max_nodes
    sorted_ids = sorted(all_ids, key=lambda nid: priority.get(nid, 0), reverse=True)
    return sorted_ids[:max_nodes]


def _is_valid_node(n: dict) -> bool:
    return bool(n.get("id") and n.get("content"))


def _is_valid_edge(e: dict) -> bool:
    return bool(e.get("id"))


def _map_edge(e: dict) -> dict:
    """Map SurrealDB edge fields (in/out) to our Edge model (from_node_id/to_node_id)."""
    mapped = dict(e)
    if "in" in mapped and "from_node_id" not in mapped:
        mapped["from_node_id"] = mapped.pop("in")
    if "out" in mapped and "to_node_id" not in mapped:
        mapped["to_node_id"] = mapped.pop("out")
    return mapped
