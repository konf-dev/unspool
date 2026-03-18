"""Tests for all db.py SQL functions."""

import pytest

from graph_lab_sql.src import db


pytestmark = pytest.mark.asyncio


async def test_save_and_get_stream_entry(user_id):
    entry = await db.save_stream_entry(user_id, "user", "hello world")
    assert entry["id"]
    assert entry["content"] == "hello world"
    assert entry["source"] == "user"

    recent = await db.get_recent_stream(user_id, limit=5)
    assert len(recent) == 1
    assert recent[0]["content"] == "hello world"


async def test_session_stream_gap(user_id):
    await db.save_stream_entry(user_id, "user", "msg1")
    entries = await db.get_session_stream(user_id, gap_hours=4)
    assert len(entries) == 1


async def test_save_and_get_node(user_id):
    node = await db.save_node(user_id, "dentist appointment")
    assert node["id"]
    assert node["content"] == "dentist appointment"

    fetched = await db.get_node(node["id"])
    assert fetched["content"] == "dentist appointment"


async def test_save_nodes_batch(user_id):
    nodes = await db.save_nodes_batch(
        user_id,
        [{"content": "task A"}, {"content": "task B"}, {"content": "task C"}],
    )
    assert len(nodes) == 3
    assert {n["content"] for n in nodes} == {"task A", "task B", "task C"}


async def test_find_node_by_content(user_id):
    await db.save_node(user_id, "Pay Rent")
    found = await db.find_node_by_content(user_id, "pay rent")
    assert found is not None
    assert found["content"] == "Pay Rent"

    not_found = await db.find_node_by_content(user_id, "nonexistent")
    assert not_found is None


async def test_get_recent_nodes(user_id):
    await db.save_node(user_id, "node1")
    await db.save_node(user_id, "node2")
    recent = await db.get_recent_nodes(user_id, limit=5)
    assert len(recent) == 2


async def test_update_node_content(user_id):
    node = await db.save_node(user_id, "old content")
    await db.update_node_content(node["id"], "new content")
    updated = await db.get_node(node["id"])
    assert updated["content"] == "new content"


async def test_delete_node(user_id):
    node = await db.save_node(user_id, "to delete")
    await db.delete_node(node["id"])
    gone = await db.get_node(node["id"])
    assert gone is None


async def test_save_edge_with_neighbor_cache(user_id):
    n1 = await db.save_node(user_id, "task")
    n2 = await db.save_node(user_id, "not done")
    edge = await db.save_edge(user_id, n1["id"], n2["id"])
    assert edge["id"]
    assert edge["from_node_id"] == n1["id"]
    assert edge["to_node_id"] == n2["id"]

    # Verify neighbor cache
    pool = await db.get_pool()
    cache = await pool.fetch(
        "SELECT * FROM node_neighbors WHERE edge_id = $1", edge["id"]
    )
    assert len(cache) == 2
    directions = {r["direction"] for r in cache}
    assert directions == {"outgoing", "incoming"}


async def test_invalidate_edge(user_id):
    n1 = await db.save_node(user_id, "meeting")
    n2 = await db.save_node(user_id, "2pm")
    edge = await db.save_edge(user_id, n1["id"], n2["id"])

    await db.invalidate_edge(edge["id"])

    # Edge should have valid_until set
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT valid_until FROM memory_edges WHERE id = $1", edge["id"]
    )
    assert row["valid_until"] is not None

    # Neighbor cache should be empty for this edge
    cache = await pool.fetch(
        "SELECT * FROM node_neighbors WHERE edge_id = $1", edge["id"]
    )
    assert len(cache) == 0

    # get_edges_from with current_only should not return it
    current = await db.get_edges_from(n1["id"], current_only=True)
    assert len(current) == 0

    # get_edges_from without filter should return it
    all_edges = await db.get_edges_from(n1["id"], current_only=False)
    assert len(all_edges) == 1


async def test_get_edges_between(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    n3 = await db.save_node(user_id, "c")
    await db.save_edge(user_id, n1["id"], n2["id"])
    await db.save_edge(user_id, n2["id"], n3["id"])

    edges = await db.get_edges_between([n1["id"], n2["id"], n3["id"]])
    assert len(edges) == 2


async def test_edge_history(user_id):
    n1 = await db.save_node(user_id, "meeting")
    n2 = await db.save_node(user_id, "2pm")
    n3 = await db.save_node(user_id, "3pm")

    e1 = await db.save_edge(user_id, n1["id"], n2["id"])
    await db.invalidate_edge(e1["id"])
    await db.save_edge(user_id, n1["id"], n3["id"])

    # History from meeting to 2pm shows invalidated edge
    history = await db.get_edge_history(n1["id"], n2["id"])
    assert len(history) == 1
    assert history[0]["valid_until"] is not None


async def test_update_edge_strength(user_id):
    n1 = await db.save_node(user_id, "x")
    n2 = await db.save_node(user_id, "y")
    await db.save_edge(user_id, n1["id"], n2["id"], strength=1.0)

    await db.update_edge_strength(n1["id"], n2["id"], 0.5)

    edges = await db.get_edges_from(n1["id"])
    assert edges[0]["strength"] == pytest.approx(0.5)


async def test_decay_edges(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    await db.save_edge(user_id, n1["id"], n2["id"], strength=1.0)

    count = await db.decay_edges(user_id, factor=0.5, min_strength=0.01)
    assert count == 1

    edges = await db.get_edges_from(n1["id"])
    assert edges[0]["strength"] == pytest.approx(0.5)


async def test_decay_exempt_edges(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    await db.save_edge(user_id, n1["id"], n2["id"], strength=1.0, decay_exempt=True)

    count = await db.decay_edges(user_id, factor=0.5, min_strength=0.01)
    assert count == 0

    edges = await db.get_edges_from(n1["id"])
    assert edges[0]["strength"] == pytest.approx(1.0)


async def test_prune_weak_edges(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    await db.save_edge(user_id, n1["id"], n2["id"], strength=0.005)

    pruned = await db.prune_weak_edges(user_id, min_strength=0.01)
    assert pruned == 1

    # Edge should be invalidated, not deleted
    all_edges = await db.get_edges_from(n1["id"], current_only=False)
    assert len(all_edges) == 1
    assert all_edges[0]["valid_until"] is not None


async def test_redirect_edges(user_id):
    old = await db.save_node(user_id, "old node")
    new = await db.save_node(user_id, "new node")
    target = await db.save_node(user_id, "target")

    await db.save_edge(user_id, old["id"], target["id"])
    await db.redirect_edges(old["id"], new["id"])

    # Old edge should be invalidated
    old_edges = await db.get_edges_from(old["id"], current_only=True)
    assert len(old_edges) == 0

    # New edge should exist
    new_edges = await db.get_edges_from(new["id"], current_only=True)
    assert len(new_edges) == 1
    assert new_edges[0]["to_node_id"] == target["id"]


async def test_rebuild_neighbor_cache(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    await db.save_edge(user_id, n1["id"], n2["id"])

    count = await db.rebuild_neighbor_cache(user_id)
    assert count == 2  # outgoing + incoming


async def test_get_neighbors(user_id):
    n1 = await db.save_node(user_id, "center")
    n2 = await db.save_node(user_id, "neighbor1")
    n3 = await db.save_node(user_id, "neighbor2")
    await db.save_edge(user_id, n1["id"], n2["id"])
    await db.save_edge(user_id, n1["id"], n3["id"])

    neighbors = await db.get_neighbors([n1["id"]])
    assert len(neighbors) == 2


async def test_find_nodes_by_status_neighbor(user_id):
    task = await db.save_node(user_id, "buy groceries")
    status = await db.save_node(user_id, "not done")
    await db.save_edge(user_id, task["id"], status["id"])

    found = await db.find_nodes_by_status_neighbor(user_id, "not done", "incoming")
    assert len(found) == 1
    assert found[0]["content"] == "buy groceries"


async def test_graph_stats(user_id):
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    await db.save_edge(user_id, n1["id"], n2["id"])
    await db.save_stream_entry(user_id, "user", "test")

    stats = await db.get_graph_stats(user_id)
    assert stats["nodes"] == 2
    assert stats["current_edges"] == 1
    assert stats["stream_entries"] == 1


async def test_reset_graph(user_id):
    await db.save_node(user_id, "a")
    await db.save_stream_entry(user_id, "user", "test")
    await db.reset_graph(user_id)

    stats = await db.get_graph_stats(user_id)
    assert stats["nodes"] == 0
    assert stats["stream_entries"] == 0
