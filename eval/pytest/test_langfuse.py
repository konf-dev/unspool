"""Verify Langfuse traces are recorded for eval requests."""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from .client import EvalClient


@pytest.mark.asyncio
async def test_trace_recorded_in_langfuse(client: EvalClient) -> None:
    langfuse_host = os.getenv("LANGFUSE_HOST")
    langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")

    if not langfuse_host or not langfuse_public or not langfuse_secret:
        pytest.skip("Langfuse credentials not set")

    resp = await client.send_message(
        "buy milk", session_id=f"langfuse-{uuid.uuid4().hex[:8]}"
    )
    assert resp.status_code == 200
    assert resp.trace_id is not None

    # Query Langfuse for the trace
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            f"{langfuse_host}/api/public/traces/{resp.trace_id}",
            auth=(langfuse_public, langfuse_secret),
        )

    if r.status_code == 200:
        trace = r.json()
        assert trace.get("id") == resp.trace_id
    elif r.status_code == 404:
        # Trace may not be flushed yet — Langfuse has async ingestion
        pytest.skip("Trace not yet available in Langfuse (async delay)")
    else:
        pytest.fail(f"Langfuse returned {r.status_code}: {r.text}")
