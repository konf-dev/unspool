"""Performance benchmarks: TTFT and total latency."""

from __future__ import annotations

import uuid

import pytest

from .client import EvalClient

TTFT_THRESHOLD_MS = 3000
TOTAL_THRESHOLD_MS = 15000
REPS = 3

PERF_CASES = [
    ("brain_dump", "I need to buy groceries and call the dentist"),
    ("query_next", "what should I do right now?"),
    ("status_done", "done with the groceries"),
    ("emotional", "I'm so overwhelmed right now"),
    ("conversation", "thanks!"),
    ("onboarding", "hey, first time here"),
    ("meta", "what can you do?"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,message", PERF_CASES, ids=[c[0] for c in PERF_CASES])
async def test_latency(client: EvalClient, name: str, message: str) -> None:
    ttfts: list[float] = []
    totals: list[float] = []

    for _ in range(REPS):
        resp = await client.send_message(
            message, session_id=f"perf-{uuid.uuid4().hex[:8]}"
        )
        assert resp.status_code == 200
        if resp.ttft_ms is not None:
            ttfts.append(resp.ttft_ms)
        totals.append(resp.latency_ms)

    if ttfts:
        p50_ttft = sorted(ttfts)[len(ttfts) // 2]
        assert p50_ttft < TTFT_THRESHOLD_MS, (
            f"{name}: p50 TTFT {p50_ttft:.0f}ms > {TTFT_THRESHOLD_MS}ms"
        )

    p50_total = sorted(totals)[len(totals) // 2]
    assert p50_total < TOTAL_THRESHOLD_MS, (
        f"{name}: p50 total {p50_total:.0f}ms > {TOTAL_THRESHOLD_MS}ms"
    )
