"""End-to-end integration tests — full graph lifecycle."""

import json
from pathlib import Path

import pytest

from graph_lab_sql.corpus.types import CorpusMessage, DayMarker
from graph_lab_sql.src import db


@pytest.mark.asyncio
async def test_full_lifecycle(user_id):
    """Create nodes, edges, correct, complete — verify graph state at each step."""
    # Step 1: Create a task with deadline
    task = await db.save_node(user_id, "email advisor")
    deadline = await db.save_node(user_id, "2026-03-20")
    not_done = await db.save_node(user_id, "not done")

    await db.save_edge(user_id, task["id"], deadline["id"])
    await db.save_edge(user_id, task["id"], not_done["id"])

    stats = await db.get_graph_stats(user_id)
    assert stats["nodes"] == 3
    assert stats["current_edges"] == 2

    # Step 2: Correct the deadline
    new_deadline = await db.save_node(user_id, "2026-03-25")
    old_edge = (await db.get_edges_from(task["id"]))[0]
    if old_edge["to_node_id"] == deadline["id"]:
        await db.invalidate_edge(old_edge["id"])
    await db.save_edge(user_id, task["id"], new_deadline["id"])

    current_edges = await db.get_edges_from(task["id"], current_only=True)
    to_ids = {e["to_node_id"] for e in current_edges}
    assert new_deadline["id"] in to_ids
    assert not_done["id"] in to_ids

    # Step 3: Complete the task
    done = await db.save_node(user_id, "done")
    not_done_edges = [
        e
        for e in await db.get_edges_from(task["id"], current_only=True)
        if e["to_node_id"] == not_done["id"]
    ]
    for e in not_done_edges:
        await db.invalidate_edge(e["id"])
    await db.save_edge(user_id, task["id"], done["id"])

    # Verify final state
    final_edges = await db.get_edges_from(task["id"], current_only=True)
    to_ids = {e["to_node_id"] for e in final_edges}
    assert done["id"] in to_ids
    assert not_done["id"] not in to_ids
    assert new_deadline["id"] in to_ids

    # Verify temporal history
    temporal = await db.get_temporal_stats(user_id)
    assert temporal["invalidated_edges"] == 2  # old deadline + not_done
    assert temporal["current_edges"] == 2  # new_deadline + done

    # Open items query should return empty
    open_tasks = await db.find_nodes_by_status_neighbor(user_id, "not done", "incoming")
    assert len(open_tasks) == 0


@pytest.mark.asyncio
async def test_neighbor_cache_consistency(user_id):
    """Verify neighbor cache stays consistent through mutations."""
    n1 = await db.save_node(user_id, "a")
    n2 = await db.save_node(user_id, "b")
    n3 = await db.save_node(user_id, "c")

    # Create edges
    e1 = await db.save_edge(user_id, n1["id"], n2["id"])
    await db.save_edge(user_id, n2["id"], n3["id"])

    # Check cache
    neighbors = await db.get_neighbors([n1["id"]])
    assert len(neighbors) == 1

    # Invalidate one edge
    await db.invalidate_edge(e1["id"])

    # Cache should reflect removal
    neighbors = await db.get_neighbors([n1["id"]])
    assert len(neighbors) == 0

    # Rebuild and verify same result
    await db.rebuild_neighbor_cache(user_id)
    neighbors = await db.get_neighbors([n1["id"]])
    assert len(neighbors) == 0

    # n2 should still have n3 as neighbor
    neighbors = await db.get_neighbors([n2["id"]])
    assert len(neighbors) == 1


@pytest.mark.asyncio
async def test_reset_cleans_everything(user_id):
    n1 = await db.save_node(user_id, "x")
    n2 = await db.save_node(user_id, "y")
    await db.save_edge(user_id, n1["id"], n2["id"])
    await db.save_stream_entry(user_id, "user", "hello")

    await db.reset_graph(user_id)

    stats = await db.get_graph_stats(user_id)
    assert stats["nodes"] == 0
    assert stats["total_edges"] == 0
    assert stats["stream_entries"] == 0
    assert stats["cache_rows"] == 0


@pytest.mark.asyncio
async def test_all_ids_are_strings(user_id):
    """Verify _row_to_dict converts UUID objects to strings everywhere."""
    stream = await db.save_stream_entry(user_id, "user", "test message")
    assert isinstance(stream["id"], str)
    assert isinstance(stream["user_id"], str)

    node = await db.save_node(user_id, "test node", source_stream_id=stream["id"])
    assert isinstance(node["id"], str)
    assert isinstance(node["user_id"], str)
    assert isinstance(node["source_stream_id"], str)

    edge = await db.save_edge(
        user_id, node["id"], node["id"], source_stream_id=stream["id"]
    )
    assert isinstance(edge["id"], str)
    assert isinstance(edge["from_node_id"], str)
    assert isinstance(edge["to_node_id"], str)

    # Verify IDs flow through triggers correctly
    from graph_lab_sql.src.triggers import trigger_recent

    result = await trigger_recent(user_id, {}, {"hours": 24, "limit": 10})
    for nid in result.node_ids:
        assert isinstance(nid, str)
        assert len(nid) == 36  # UUID format


def test_corpus_jsonl_parseable():
    """Verify the corpus JSONL files from graph_lab can be parsed."""
    corpus_dir = (
        Path(__file__).parent.parent.parent
        / "graph_lab"
        / "corpus"
        / "output"
        / "latest"
    )
    if not corpus_dir.exists():
        pytest.skip("Corpus not generated yet")

    jsonl_files = list(corpus_dir.glob("*.jsonl"))
    assert len(jsonl_files) > 0, f"No .jsonl files in {corpus_dir}"

    for path in jsonl_files:
        msg_count = 0
        day_count = 0
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("type") == "day_marker":
                    DayMarker(**data)
                    day_count += 1
                else:
                    CorpusMessage(**data)
                    msg_count += 1

        assert msg_count > 0, f"{path.name}: no messages found"
        assert day_count > 0, f"{path.name}: no day markers found"
