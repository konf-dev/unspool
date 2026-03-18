"""Tests for bi-temporal edge behavior."""

import pytest

from graph_lab_sql.src import db

pytestmark = pytest.mark.asyncio


async def test_correction_flow(user_id):
    """Simulate: 'meeting at 2pm' then 'actually moved to 3pm'."""
    meeting = await db.save_node(user_id, "team meeting")
    time_2pm = await db.save_node(user_id, "2pm")
    time_3pm = await db.save_node(user_id, "3pm")

    # Original edge
    edge_old = await db.save_edge(user_id, meeting["id"], time_2pm["id"])

    # Correction: invalidate old, create new
    await db.invalidate_edge(edge_old["id"])
    await db.save_edge(user_id, meeting["id"], time_3pm["id"])

    # Current edges should only show 3pm
    current = await db.get_edges_from(meeting["id"], current_only=True)
    assert len(current) == 1
    assert current[0]["to_node_id"] == time_3pm["id"]

    # All edges should show both
    all_edges = await db.get_edges_from(meeting["id"], current_only=False)
    assert len(all_edges) == 2

    # Neighbor cache should only contain 3pm
    neighbors = await db.get_neighbors([meeting["id"]])
    neighbor_ids = {n["neighbor_id"] for n in neighbors}
    assert time_3pm["id"] in neighbor_ids
    assert time_2pm["id"] not in neighbor_ids


async def test_multiple_corrections(user_id):
    """Multiple corrections on the same node."""
    appt = await db.save_node(user_id, "dentist")
    mon = await db.save_node(user_id, "Monday")
    tue = await db.save_node(user_id, "Tuesday")
    wed = await db.save_node(user_id, "Wednesday")

    e1 = await db.save_edge(user_id, appt["id"], mon["id"])
    await db.invalidate_edge(e1["id"])

    e2 = await db.save_edge(user_id, appt["id"], tue["id"])
    await db.invalidate_edge(e2["id"])

    await db.save_edge(user_id, appt["id"], wed["id"])

    current = await db.get_edges_from(appt["id"], current_only=True)
    assert len(current) == 1
    assert current[0]["to_node_id"] == wed["id"]

    all_edges = await db.get_edges_from(appt["id"], current_only=False)
    assert len(all_edges) == 3

    temporal = await db.get_temporal_stats(user_id)
    assert temporal["total_edges"] == 3
    assert temporal["current_edges"] == 1
    assert temporal["invalidated_edges"] == 2


async def test_completion_invalidates_not_done(user_id):
    """When task is done, 'not done' edge gets invalidated."""
    task = await db.save_node(user_id, "buy groceries")
    not_done = await db.save_node(user_id, "not done")
    done = await db.save_node(user_id, "done")

    not_done_edge = await db.save_edge(user_id, task["id"], not_done["id"])

    # Complete the task
    await db.invalidate_edge(not_done_edge["id"])
    await db.save_edge(user_id, task["id"], done["id"])

    # Task should only be connected to "done" in current edges
    current = await db.get_edges_from(task["id"], current_only=True)
    assert len(current) == 1
    assert current[0]["to_node_id"] == done["id"]

    # Status neighbor query should not find this task as "not done"
    open_tasks = await db.find_nodes_by_status_neighbor(user_id, "not done", "incoming")
    assert len(open_tasks) == 0


async def test_decay_preserves_exempt(user_id):
    """decay_exempt edges survive decay cycles."""
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    n3 = await db.save_node(user_id, "c")

    # Regular edge
    await db.save_edge(user_id, n1["id"], n2["id"], strength=1.0)
    # Exempt edge
    await db.save_edge(user_id, n1["id"], n3["id"], strength=1.0, decay_exempt=True)

    # Decay
    await db.decay_edges(user_id, factor=0.1, min_strength=0.01)

    edges = await db.get_edges_from(n1["id"])
    strengths = {e["to_node_id"]: e["strength"] for e in edges}

    assert strengths[n2["id"]] == pytest.approx(0.1)
    assert strengths[n3["id"]] == pytest.approx(1.0)


async def test_prune_invalidates_not_deletes(user_id):
    """Pruning weak edges should invalidate them, preserving history."""
    n1 = await db.save_node(user_id, "x")
    n2 = await db.save_node(user_id, "y")
    await db.save_edge(user_id, n1["id"], n2["id"], strength=0.001)

    pruned = await db.prune_weak_edges(user_id, min_strength=0.01)
    assert pruned == 1

    # Edge still exists in DB but is invalidated
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM memory_edges WHERE from_node_id = $1 AND to_node_id = $2",
        n1["id"],
        n2["id"],
    )
    assert row is not None
    assert row["valid_until"] is not None


async def test_edge_history_ordering(user_id):
    """Edge history should be ordered by valid_from."""
    n1 = await db.save_node(user_id, "task")
    n2 = await db.save_node(user_id, "status")

    e1 = await db.save_edge(user_id, n1["id"], n2["id"])
    await db.invalidate_edge(e1["id"])
    await db.save_edge(user_id, n1["id"], n2["id"])

    history = await db.get_edge_history(n1["id"], n2["id"])
    assert len(history) == 2
    assert history[0]["valid_until"] is not None  # first is invalidated
    assert history[1]["valid_until"] is None  # second is current
