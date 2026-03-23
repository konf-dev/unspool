"""Tests for cold path extraction."""

import pytest
from src.agents.cold_path.extractor import _idempotency_key


class TestIdempotency:
    def test_same_input_same_key(self):
        """Same user_id + message produces same idempotency key."""
        key1 = _idempotency_key("user1", "hello world")
        key2 = _idempotency_key("user1", "hello world")
        assert key1 == key2

    def test_different_input_different_key(self):
        """Different messages produce different keys."""
        key1 = _idempotency_key("user1", "hello world")
        key2 = _idempotency_key("user1", "goodbye world")
        assert key1 != key2

    def test_different_user_different_key(self):
        """Different users with same message produce different keys."""
        key1 = _idempotency_key("user1", "hello world")
        key2 = _idempotency_key("user2", "hello world")
        assert key1 != key2


class TestExtractionSchemas:
    def test_extraction_result_parses(self):
        """ExtractionResult can be instantiated."""
        from src.agents.cold_path.schemas import ExtractionResult, ExtractedNode, ExtractedEdge

        result = ExtractionResult(
            nodes=[ExtractedNode(content="Buy milk", node_type="action")],
            edges=[ExtractedEdge(
                source_content="Buy milk",
                target_content="OPEN",
                edge_type="IS_STATUS",
            )],
        )
        assert len(result.nodes) == 1
        assert result.nodes[0].content == "Buy milk"
        assert len(result.edges) == 1

    def test_empty_extraction(self):
        """Empty extraction is valid."""
        from src.agents.cold_path.schemas import ExtractionResult

        result = ExtractionResult(nodes=[], edges=[])
        assert len(result.nodes) == 0
        assert len(result.edges) == 0
