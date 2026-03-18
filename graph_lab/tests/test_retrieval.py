"""Tests for trigger chain and subgraph assembly."""

from graph_lab.src.types import ActiveSubgraph, Edge, Node, TriggerResult


def test_active_subgraph_construction():
    """Verify ActiveSubgraph can be built from components."""
    nodes = [
        Node(
            id="node:1",
            user_id="test",
            content="rent",
            created_at="2026-03-16T00:00:00Z",
            last_activated_at="2026-03-16T00:00:00Z",
        ),
        Node(
            id="node:2",
            user_id="test",
            content="2026-03-20",
            created_at="2026-03-16T00:00:00Z",
            last_activated_at="2026-03-16T00:00:00Z",
        ),
    ]
    edges = [
        Edge(
            id="edge:1",
            user_id="test",
            from_node_id="node:1",
            to_node_id="node:2",
            created_at="2026-03-16T00:00:00Z",
            last_traversed_at="2026-03-16T00:00:00Z",
        ),
    ]
    triggers = [
        TriggerResult(trigger_name="semantic", node_ids=["node:1", "node:2"]),
    ]

    subgraph = ActiveSubgraph(nodes=nodes, edges=edges, trigger_results=triggers)
    assert len(subgraph.nodes) == 2
    assert len(subgraph.edges) == 1
    assert subgraph.trigger_results[0].trigger_name == "semantic"


def test_prioritize_quick_nodes_first():
    """Quick ingest nodes should get highest priority."""
    from graph_lab.src.retrieval import _prioritize_nodes

    quick_nodes = [{"id": "node:1"}, {"id": "node:2"}]
    trigger_results = [
        TriggerResult(trigger_name="semantic", node_ids=["node:3", "node:4", "node:5"]),
    ]

    all_ids = ["node:1", "node:2", "node:3", "node:4", "node:5"]
    prioritized = _prioritize_nodes(all_ids, quick_nodes, trigger_results, max_nodes=3)

    assert len(prioritized) == 3
    assert "node:1" in prioritized
    assert "node:2" in prioritized
