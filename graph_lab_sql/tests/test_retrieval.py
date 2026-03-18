"""Tests for trigger chain and neighbor-based retrieval."""

import pytest

from graph_lab_sql.src import db
from graph_lab_sql.src.triggers import trigger_recent, trigger_status, trigger_walk

pytestmark = pytest.mark.asyncio


async def test_trigger_status_open_items(user_id):
    task1 = await db.save_node(user_id, "buy groceries")
    task2 = await db.save_node(user_id, "pay rent")
    status = await db.save_node(user_id, "not done")
    await db.save_edge(user_id, task1["id"], status["id"])
    await db.save_edge(user_id, task2["id"], status["id"])

    result = await trigger_status(
        user_id,
        context={},
        params={"status": "not done", "direction": "incoming"},
    )
    assert len(result.node_ids) == 2


async def test_trigger_status_excludes_completed(user_id):
    """Task connected to 'not done' with invalidated edge should not appear."""
    task = await db.save_node(user_id, "buy groceries")
    not_done = await db.save_node(user_id, "not done")
    edge = await db.save_edge(user_id, task["id"], not_done["id"])
    await db.invalidate_edge(edge["id"])

    result = await trigger_status(
        user_id,
        context={},
        params={"status": "not done", "direction": "incoming"},
    )
    assert len(result.node_ids) == 0


async def test_trigger_recent(user_id):
    await db.save_node(user_id, "recently mentioned")
    result = await trigger_recent(
        user_id,
        context={},
        params={"hours": 24, "limit": 10},
    )
    assert len(result.node_ids) == 1


async def test_trigger_walk(user_id):
    center = await db.save_node(user_id, "center")
    neighbor = await db.save_node(user_id, "neighbor")
    await db.save_edge(user_id, center["id"], neighbor["id"])

    result = await trigger_walk(
        user_id,
        context={"collected_node_ids": {str(center["id"])}},
        params={"max_nodes": 30},
    )
    assert str(neighbor["id"]) in result.node_ids


async def test_trigger_walk_empty(user_id):
    result = await trigger_walk(
        user_id,
        context={"collected_node_ids": set()},
        params={"max_nodes": 30},
    )
    assert len(result.node_ids) == 0
