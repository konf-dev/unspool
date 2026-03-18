"""Tests for ingest correction parsing and content resolution."""

import pytest

from graph_lab_sql.src import db
from graph_lab_sql.src.ingest import _apply_correction, _resolve_content_to_id
from graph_lab_sql.src.types import Correction

pytestmark = pytest.mark.asyncio


async def test_resolve_content_to_id_existing(user_id):
    node = await db.save_node(user_id, "buy groceries")
    cache: dict[str, str] = {}
    result = await _resolve_content_to_id(user_id, "buy groceries", cache)
    assert result == node["id"]
    assert "buy groceries" in cache


async def test_resolve_content_to_id_status_node(user_id):
    cache: dict[str, str] = {}
    result = await _resolve_content_to_id(user_id, "not done", cache)
    assert result is not None
    # Should have created the node
    node = await db.find_node_by_content(user_id, "not done")
    assert node is not None


async def test_resolve_content_to_id_unknown(user_id):
    cache: dict[str, str] = {}
    result = await _resolve_content_to_id(user_id, "nonexistent random thing", cache)
    assert result is None


async def test_apply_correction_explicit(user_id):
    """Test the full correction flow: target → old_value gets invalidated, target → new_value created."""
    target = await db.save_node(user_id, "meeting with team")
    old_val = await db.save_node(user_id, "2pm")
    await db.save_edge(user_id, target["id"], old_val["id"])

    correction = Correction(
        target_content="meeting with team",
        old_value="2pm",
        new_value="3pm",
        correction_type="explicit",
    )
    cache: dict[str, str] = {}
    result = await _apply_correction(user_id, correction, cache, stream_id=None)
    assert result is True

    # Old edge should be invalidated
    old_edges = await db.get_edges_from(target["id"], current_only=True)
    old_targets = [e["to_node_id"] for e in old_edges]
    assert old_val["id"] not in old_targets

    # New node "3pm" should exist and be connected
    new_node = await db.find_node_by_content(user_id, "3pm")
    assert new_node is not None
    assert new_node["id"] in old_targets


async def test_apply_correction_target_not_found(user_id):
    correction = Correction(
        target_content="nonexistent thing",
        old_value="x",
        new_value="y",
        correction_type="explicit",
    )
    cache: dict[str, str] = {}
    result = await _apply_correction(user_id, correction, cache, stream_id=None)
    assert result is False


async def test_apply_correction_old_value_not_found(user_id):
    """Should still create the new edge even if old edge not found."""
    target = await db.save_node(user_id, "dentist")
    # No edge to old value exists

    correction = Correction(
        target_content="dentist",
        old_value="Monday",
        new_value="Tuesday",
        correction_type="explicit",
    )
    cache: dict[str, str] = {}
    result = await _apply_correction(user_id, correction, cache, stream_id=None)
    assert result is True

    # New edge should be created
    edges = await db.get_edges_from(target["id"], current_only=True)
    assert len(edges) == 1
    new_node = await db.get_node(edges[0]["to_node_id"])
    assert new_node["content"] == "Tuesday"
