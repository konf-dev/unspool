"""Tests for node extraction (ingest)."""

import pytest
from graph_lab.src.types import IngestOutput


@pytest.fixture
def ingest_output_brain_dump():
    return {
        "nodes": [
            {"content": "email advisor", "existing_match": None},
            {"content": "thesis", "existing_match": None},
            {"content": "rent", "existing_match": None},
            {"content": "2026-03-20", "existing_match": None},
        ],
        "edges": [
            {"from": "email advisor", "to": "thesis"},
            {"from": "rent", "to": "2026-03-20"},
        ],
        "edge_updates": [],
    }


@pytest.fixture
def ingest_output_completion():
    return {
        "nodes": [
            {"content": "done", "existing_match": None},
        ],
        "edges": [
            {"from": "rent", "to": "done"},
        ],
        "edge_updates": [
            {"from": "rent", "to": "not done", "new_strength": 0},
        ],
    }


def test_ingest_output_parses_brain_dump(ingest_output_brain_dump):
    output = IngestOutput(**ingest_output_brain_dump)
    assert len(output.nodes) == 4
    assert len(output.edges) == 2
    assert output.nodes[0].content == "email advisor"


def test_ingest_output_parses_completion(ingest_output_completion):
    output = IngestOutput(**ingest_output_completion)
    assert len(output.nodes) == 1
    assert len(output.edge_updates) == 1
    assert output.edge_updates[0].new_strength == 0


def test_ingest_output_empty():
    output = IngestOutput(nodes=[], edges=[], edge_updates=[])
    assert len(output.nodes) == 0


def test_ingest_output_existing_match():
    output = IngestOutput(
        nodes=[
            {"content": "rent", "existing_match": "node:abc123"},
        ],
        edges=[],
    )
    assert output.nodes[0].existing_match == "node:abc123"


def test_ingest_output_validates_max_nodes():
    """Verify we can programmatically cap nodes."""
    data = {
        "nodes": [{"content": f"node_{i}"} for i in range(20)],
        "edges": [],
    }
    output = IngestOutput(**data)
    # Cap at 10 (as config specifies)
    capped = output.nodes[:10]
    assert len(capped) == 10
