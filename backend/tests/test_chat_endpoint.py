"""Integration tests for /api/chat endpoint using httpx.AsyncClient."""

import contextlib
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.supabase_auth import get_current_user
from src.main import app


def _override_auth(user_id: str = "test-user-123"):
    """Override FastAPI's auth dependency to return a fixed user_id."""
    app.dependency_overrides[get_current_user] = lambda: user_id


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)


def _chat_patches(**extra_patches) -> contextlib.ExitStack:
    """Enter all common patches for chat endpoint tests."""
    stack = contextlib.ExitStack()
    stack.enter_context(
        patch(
            "src.api.chat.db.save_message",
            new_callable=AsyncMock,
            return_value={"id": "msg-001", "role": "user", "content": "test"},
        )
    )
    stack.enter_context(
        patch(
            "src.api.chat.redis.session_get", new_callable=AsyncMock, return_value=None
        )
    )
    stack.enter_context(patch("src.api.chat.redis.session_set", new_callable=AsyncMock))
    stack.enter_context(
        patch(
            "src.api.chat.redis.rate_limit_check",
            new_callable=AsyncMock,
            return_value=(True, 9),
        )
    )
    stack.enter_context(
        patch(
            "src.api.chat.db.get_user_tier", new_callable=AsyncMock, return_value="free"
        )
    )
    stack.enter_context(patch("src.api.chat.dispatch_job", new_callable=AsyncMock))
    stack.enter_context(patch("src.api.chat._check_gate", new_callable=AsyncMock))
    for target, mock in extra_patches.items():
        stack.enter_context(patch(target, side_effect=mock))
    return stack


def _parse_sse_events(body: str) -> list[dict]:
    """Parse SSE event stream into list of JSON payloads."""
    events = []
    for line in body.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line.removeprefix("data: ")))
            except json.JSONDecodeError:
                pass
    return events


@pytest.mark.asyncio
class TestChatEndpointAuth:
    async def test_missing_auth_returns_401(self) -> None:
        _clear_auth_override()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                json={"message": "hello", "session_id": "s1"},
            )
        assert response.status_code == 401

    async def test_invalid_auth_returns_401(self) -> None:
        _clear_auth_override()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                json={"message": "hello", "session_id": "s1"},
                headers={"Authorization": "Bearer invalid-token"},
            )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestChatEndpointHappyPath:
    async def test_sse_stream_returns_tokens_and_done(self) -> None:
        """Happy path: SSE stream should contain token events followed by done."""

        async def mock_stream_response(user_id, message, trace_id, context_out):
            yield 'data: {"type": "token", "content": "Hello "}\n\n'
            yield 'data: {"type": "token", "content": "there!"}\n\n'
            yield 'data: {"type": "done"}\n\n'

        _override_auth()
        try:
            with _chat_patches(
                **{"src.api.chat._stream_response": mock_stream_response}
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/chat",
                        json={"message": "hello", "session_id": "s1"},
                        headers={"Authorization": "Bearer valid-token"},
                    )

                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                assert "X-Trace-Id" in response.headers

                events = _parse_sse_events(response.text)
                token_events = [e for e in events if e.get("type") == "token"]
                done_events = [e for e in events if e.get("type") == "done"]
                assert len(token_events) >= 1
                assert len(done_events) == 1
        finally:
            _clear_auth_override()


@pytest.mark.asyncio
class TestChatEndpointErrors:
    async def test_pipeline_crash_returns_error_message(self) -> None:
        """When pipeline crashes, user should get an error message via SSE."""

        async def mock_crash(*args, **kwargs):
            raise RuntimeError("LLM API down")
            yield  # noqa: RUF027

        _override_auth()
        try:
            with _chat_patches(**{"src.api.chat._stream_response": mock_crash}):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/chat",
                        json={"message": "hello", "session_id": "s1"},
                        headers={"Authorization": "Bearer valid-token"},
                    )

                assert response.status_code == 200
                events = _parse_sse_events(response.text)
                error_tokens = [
                    e
                    for e in events
                    if e.get("type") == "token"
                    and "sorry" in e.get("content", "").lower()
                ]
                assert len(error_tokens) >= 1
        finally:
            _clear_auth_override()

    async def test_timeout_returns_timeout_message(self) -> None:
        """When pipeline times out, user should get a timeout message."""

        async def mock_timeout(*args, **kwargs):
            raise TimeoutError("Pipeline timed out")
            yield  # noqa: RUF027

        _override_auth()
        try:
            with _chat_patches(**{"src.api.chat._stream_response": mock_timeout}):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/chat",
                        json={"message": "hello", "session_id": "s1"},
                        headers={"Authorization": "Bearer valid-token"},
                    )

                assert response.status_code == 200
                events = _parse_sse_events(response.text)
                timeout_tokens = [
                    e
                    for e in events
                    if e.get("type") == "token"
                    and "too long" in e.get("content", "").lower()
                ]
                assert len(timeout_tokens) >= 1
        finally:
            _clear_auth_override()
