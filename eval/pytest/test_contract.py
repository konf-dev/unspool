"""Contract tests: auth, SSE format, headers, admin API."""

from __future__ import annotations

import uuid

import httpx
import pytest

from .admin import AdminClient
from .client import EvalClient
from .conftest import EVAL_USER_ID


@pytest.mark.asyncio
async def test_no_token_returns_401(api_url: str) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as http:
        r = await http.post(
            "/api/chat",
            json={"message": "hi", "session_id": "test"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bad_token_returns_401(api_url: str) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as http:
        r = await http.post(
            "/api/chat",
            json={"message": "hi", "session_id": "test"},
            headers={"Authorization": "Bearer bad-token-value"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_eval_token_returns_sse(client: EvalClient) -> None:
    resp = await client.send_message(
        "hi", session_id=f"contract-{uuid.uuid4().hex[:8]}"
    )
    assert resp.status_code == 200
    assert resp.response_text, "Expected non-empty response text"
    assert resp.trace_id, "Expected X-Trace-Id header"


@pytest.mark.asyncio
async def test_sse_format(client: EvalClient) -> None:
    resp = await client.send_message(
        "hello", session_id=f"contract-{uuid.uuid4().hex[:8]}"
    )
    assert resp.status_code == 200

    # Should have at least one token event and one done event
    token_events = [e for e in resp.events if e.get("type") == "token"]
    done_events = [e for e in resp.events if e.get("type") == "done"]
    assert len(token_events) > 0, "Expected at least one token event"
    assert len(done_events) == 1, "Expected exactly one done event"

    # Token events should have content
    for event in token_events:
        assert "content" in event, f"Token event missing content: {event}"


@pytest.mark.asyncio
async def test_sse_content_type(api_url: str, eval_api_key: str) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=60) as http:
        async with http.stream(
            "POST",
            "/api/chat",
            json={"message": "hi", "session_id": f"contract-{uuid.uuid4().hex[:8]}"},
            headers={
                "Authorization": f"Bearer eval:{eval_api_key}",
                "Content-Type": "application/json",
            },
        ) as response:
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type


@pytest.mark.asyncio
async def test_trace_id_header(client: EvalClient) -> None:
    resp = await client.send_message(
        "test trace", session_id=f"contract-{uuid.uuid4().hex[:8]}"
    )
    assert resp.trace_id is not None
    # Should be a valid UUID
    uuid.UUID(resp.trace_id)


@pytest.mark.asyncio
async def test_admin_cleanup_works(admin: AdminClient) -> None:
    result = await admin.cleanup()
    assert "user_id" in result
    assert result["user_id"] == EVAL_USER_ID


@pytest.mark.asyncio
async def test_admin_items_returns_list(admin: AdminClient) -> None:
    items = await admin.get_items(EVAL_USER_ID)
    assert isinstance(items, list)
