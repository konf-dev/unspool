"""Shared test fixtures for graph_lab tests."""

import asyncio
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_llm_generate():
    """Mock LLM generate to avoid real API calls in tests."""
    with patch("graph_lab.src.llm.generate") as mock:
        mock.return_value = "mocked response"
        yield mock


@pytest.fixture
def mock_llm_generate_json():
    """Mock LLM generate_json to avoid real API calls in tests."""
    with patch("graph_lab.src.llm.generate_json") as mock:
        mock.return_value = {"nodes": [], "edges": [], "edge_updates": []}
        yield mock


@pytest.fixture
def mock_embedding():
    """Mock embedding generation."""
    with patch("graph_lab.src.embedding.generate_embedding") as mock:
        mock.return_value = [0.1] * 1536
        yield mock


@pytest.fixture
def mock_embeddings_batch():
    """Mock batch embedding generation."""
    with patch("graph_lab.src.embedding.generate_embeddings_batch") as mock:

        async def _batch(texts, model=None):
            return [[0.1] * 1536 for _ in texts]

        mock.side_effect = _batch
        yield mock


TEST_USER_ID = "test-user-fixtures"
