"""Tests for subgraph serialization."""

from datetime import datetime, timezone

from graph_lab.src.serialization import count_tokens, serialize_subgraph
from graph_lab.src.types import ActiveSubgraph, Edge, Node

_DEFAULT_DT = datetime(2026, 3, 16, tzinfo=timezone.utc)


def _make_node(id: str, content: str, **kwargs) -> Node:
    return Node(
        id=id,
        user_id="test",
        content=content,
        created_at=kwargs.get("created_at", _DEFAULT_DT),
        last_activated_at=kwargs.get("last_activated_at", _DEFAULT_DT),
    )


def _make_edge(id: str, from_id: str, to_id: str, strength: float = 1.0) -> Edge:
    return Edge(
        id=id,
        user_id="test",
        from_node_id=from_id,
        to_node_id=to_id,
        strength=strength,
        created_at=datetime(2026, 3, 16, tzinfo=timezone.utc),
        last_traversed_at=datetime(2026, 3, 16, tzinfo=timezone.utc),
    )


def test_serialize_empty_subgraph():
    subgraph = ActiveSubgraph()
    result = serialize_subgraph(subgraph, "hello")
    assert "<context>" in result
    assert "</context>" in result
    assert "Current time:" in result


def test_serialize_with_open_items():
    nodes = [
        _make_node("n1", "email advisor"),
        _make_node("n2", "not done"),
    ]
    edges = [_make_edge("e1", "n1", "n2")]
    subgraph = ActiveSubgraph(nodes=nodes, edges=edges)

    result = serialize_subgraph(subgraph, "what should I do")
    assert "OPEN" in result
    assert "email advisor" in result


def test_serialize_with_date_nodes():
    nodes = [
        _make_node("n1", "rent"),
        _make_node("n2", "2026-03-18"),
        _make_node("n3", "not done"),
    ]
    edges = [
        _make_edge("e1", "n1", "n2"),
        _make_edge("e2", "n1", "n3"),
    ]
    subgraph = ActiveSubgraph(nodes=nodes, edges=edges)

    result = serialize_subgraph(subgraph, "what's coming up")
    assert "<context>" in result


def test_serialize_suppressed_items():
    nodes = [
        _make_node("n1", "rent"),
        _make_node("n2", "surfaced"),
    ]
    edges = [_make_edge("e1", "n1", "n2")]
    subgraph = ActiveSubgraph(nodes=nodes, edges=edges)

    result = serialize_subgraph(subgraph, "hey")
    assert "RECENTLY SURFACED" in result
    assert "rent" in result


def test_token_counting():
    text = "Hello world, this is a test"
    tokens = count_tokens(text)
    assert tokens > 0
    assert tokens < 20


def test_serialize_stays_within_budget():
    """Verify serialization respects token budget."""
    # Create a large subgraph
    nodes = [_make_node(f"n{i}", f"concept number {i}") for i in range(50)]
    nodes.append(_make_node("nd", "not done"))
    edges = [_make_edge(f"e{i}", f"n{i}", "nd") for i in range(50)]
    subgraph = ActiveSubgraph(nodes=nodes, edges=edges)

    result = serialize_subgraph(subgraph, "test")
    tokens = count_tokens(result)
    # Should be within reasonable budget (2000 tokens default + some overhead)
    assert tokens < 3000
