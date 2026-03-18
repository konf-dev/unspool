"""Trigger chain orchestration — builds the active subgraph for reasoning."""

import asyncio

from src.graph import db
from src.graph.triggers import get_trigger
from src.graph.types import ActiveSubgraph, Edge, Node, TriggerResult
from src.orchestrator.config_loader import load_config
from src.telemetry.logger import get_logger

_log = get_logger("graph.retrieval")


async def build_active_subgraph(
    user_id: str,
    message: str,
    message_embedding: list[float] | None,
    quick_nodes: list[dict],
) -> ActiveSubgraph:
    graph_config = load_config("graph")
    trigger_config = load_config("triggers")

    retrieval = graph_config.get("retrieval", {})
    max_nodes = retrieval.get("max_subgraph_nodes", 50)

    triggers = trigger_config.get("triggers", {})

    context = {
        "message": message,
        "message_embedding": message_embedding,
        "quick_node_ids": [n["id"] for n in quick_nodes],
        "collected_node_ids": set(str(n["id"]) for n in quick_nodes),
    }

    independent: list[tuple[str, dict]] = []
    dependent: list[tuple[str, dict]] = []

    for name, tdef in triggers.items():
        if not tdef.get("enabled", True):
            continue
        if tdef.get("depends_on"):
            dependent.append((name, tdef))
        else:
            independent.append((name, tdef))

    trigger_results: list[TriggerResult] = []

    if independent:
        tasks = [
            _run_trigger(name, user_id, context, tdef) for name, tdef in independent
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                _log.warning("graph.trigger_failed", error=str(result))
                continue
            tr: TriggerResult = result
            trigger_results.append(tr)
            context["collected_node_ids"].update(tr.node_ids)

    for name, tdef in dependent:
        try:
            result = await _run_trigger(name, user_id, context, tdef)
            trigger_results.append(result)
            context["collected_node_ids"].update(result.node_ids)
        except Exception as e:
            _log.warning("graph.trigger_failed", trigger=name, error=str(e))

    all_ids = list(context["collected_node_ids"])

    if len(all_ids) > max_nodes:
        all_ids = _prioritize_nodes(all_ids, quick_nodes, trigger_results, max_nodes)

    nodes_raw = await db.get_nodes_by_ids(all_ids)
    edges_raw = await db.get_edges_between(all_ids)

    await db.update_nodes_last_activated(all_ids)

    nodes = [Node(**_map_node(n)) for n in nodes_raw if _is_valid_node(n)]
    edges = [Edge(**_map_edge(e)) for e in edges_raw if _is_valid_edge(e)]

    _log.info(
        "graph.subgraph_built",
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


async def _run_trigger(
    name: str, user_id: str, context: dict, tdef: dict
) -> TriggerResult:
    trigger_fn = get_trigger(tdef["type"])
    if not trigger_fn:
        _log.warning("graph.trigger_not_found", name=name, type=tdef["type"])
        return TriggerResult(trigger_name=name)
    return await trigger_fn(user_id, context, tdef.get("params", {}))


def _prioritize_nodes(
    all_ids: list[str],
    quick_nodes: list[dict],
    trigger_results: list[TriggerResult],
    max_nodes: int,
) -> list[str]:
    priority: dict[str, int] = {}

    for n in quick_nodes:
        priority[str(n["id"])] = 100

    specific = {"temporal", "status_not_done", "status_surfaced"}
    for tr in trigger_results:
        is_specific = any(s in tr.trigger_name for s in specific)
        score = 50 if is_specific else 10
        for nid in tr.node_ids:
            priority[nid] = max(priority.get(nid, 0), score)

    sorted_ids = sorted(all_ids, key=lambda nid: priority.get(nid, 0), reverse=True)
    return sorted_ids[:max_nodes]


def _is_valid_node(n: dict) -> bool:
    return bool(n.get("id") and n.get("content"))


def _is_valid_edge(e: dict) -> bool:
    return bool(e.get("id"))


def _map_node(n: dict) -> dict:
    mapped = dict(n)
    for key in ("id", "user_id", "source_message_id"):
        if key in mapped and mapped[key] is not None:
            mapped[key] = str(mapped[key])
    return mapped


def _map_edge(e: dict) -> dict:
    mapped = dict(e)
    for key in ("id", "user_id", "from_node_id", "to_node_id", "source_message_id"):
        if key in mapped and mapped[key] is not None:
            mapped[key] = str(mapped[key])
    return mapped
