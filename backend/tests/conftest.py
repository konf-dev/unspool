"""Pytest fixtures for backend tests."""

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


# Ensure test environment
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def eval_user_id() -> str:
    return "b8a2e17e-ff55-485f-ad6c-29055a607b33"


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("src.db.redis.get_redis") as mock:
        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.delete = AsyncMock(return_value=True)
        redis_mock.incr = AsyncMock(return_value=1)
        pipe_mock = MagicMock()
        pipe_mock.set = MagicMock(return_value=pipe_mock)
        pipe_mock.incr = MagicMock(return_value=pipe_mock)
        pipe_mock.exec = AsyncMock(return_value=[True, 1])
        redis_mock.pipeline = MagicMock(return_value=pipe_mock)
        mock.return_value = redis_mock
        yield redis_mock


@pytest.fixture
def mock_qstash():
    """Mock QStash client."""
    with patch("src.integrations.qstash._get_client") as mock:
        client_mock = AsyncMock()
        client_mock.message.publish_json = AsyncMock(return_value=MagicMock(message_id="test-msg-id"))
        client_mock.schedule.create = AsyncMock(return_value="test-schedule-id")
        client_mock.schedule.list = AsyncMock(return_value=[])
        client_mock.schedule.delete = AsyncMock()
        mock.return_value = client_mock
        yield client_mock


@pytest.fixture
def auth_headers(test_user_id: str) -> dict[str, str]:
    """Headers with a mock auth token. Requires patching get_current_user."""
    return {"Authorization": f"Bearer mock-jwt-{test_user_id}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Admin-Key": "test-admin-key"}
