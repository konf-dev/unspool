"""Eval runner: two-phase E2E testing against the deployed API.

Phase 1 (send_all_scenarios): Fire messages to Railway, collect responses + trace IDs.
Phase 2 (enrich_from_langfuse): Batch-fetch tool call data from Langfuse after ingestion.
"""

import asyncio
import json
import os
import uuid
from typing import Any

import httpx

API_URL = os.environ.get("EVAL_API_URL", "https://api.unspool.life")
EVAL_API_KEY = os.environ.get("EVAL_API_KEY", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")


async def cleanup_eval_user() -> None:
    """Delete all data for the eval user before a run."""
    if not ADMIN_API_KEY:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(
            f"{API_URL}/admin/eval-cleanup",
            headers={"X-Admin-Key": ADMIN_API_KEY},
        )


async def send_message(message: str, session_id: str) -> "EvalResult":
    """POST to /api/chat, parse SSE stream. Returns an EvalResult (no Langfuse data yet)."""
    async with httpx.AsyncClient(timeout=90) as client:
        async with client.stream(
            "POST",
            f"{API_URL}/api/chat",
            json={"message": message, "session_id": session_id},
            headers={
                "Authorization": f"Bearer eval:{EVAL_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            # Railway edge may add its own X-Trace-Id — take the first one (ours)
            raw_trace = resp.headers.get("x-trace-id", "")
            trace_id = raw_trace.split(",")[0].strip()

            tokens: list[str] = []
            tool_names_sse: list[str] = []

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line.removeprefix("data: "))
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "token":
                    tokens.append(event.get("content", ""))
                elif (
                    event.get("type") == "tool_status" and event.get("status") == "done"
                ):
                    tool_names_sse.append(event.get("tool", ""))

            return EvalResult(
                response="".join(tokens),
                tool_names_sse=tool_names_sse,
                trace_id=trace_id,
                session_id=session_id,
            )


async def run_eval_scenario(
    conversation: list[dict[str, str]],
    **kwargs: Any,
) -> "EvalResult":
    """Compat wrapper: send a single scenario's conversation and return the result.

    Used by Layer 1 eval tests (conversation_quality, personality, etc.).
    Does NOT fetch Langfuse data — those tests only need the response text.
    """
    session_id = f"eval-{uuid.uuid4().hex[:12]}"
    result: EvalResult | None = None
    for turn in conversation:
        if turn["role"] != "user":
            continue
        result = await send_message(turn["content"], session_id)
    if not result:
        return EvalResult(response="", tool_names_sse=[], trace_id="", session_id="")
    return result


async def send_all_scenarios(
    scenarios: list[dict[str, Any]],
) -> dict[str, "EvalResult"]:
    """Phase 1: Send all scenario messages to Railway sequentially.

    Returns {scenario_id: EvalResult} with response + SSE data (no Langfuse yet).
    """
    results: dict[str, EvalResult] = {}

    for scenario in scenarios:
        scenario_id = scenario["id"]
        session_id = f"eval-{uuid.uuid4().hex[:12]}"

        # Send each turn in the conversation
        result: EvalResult | None = None
        for turn in scenario["conversation"]:
            if turn["role"] != "user":
                continue
            result = await send_message(turn["content"], session_id)

        if result:
            results[scenario_id] = result

    return results


async def enrich_from_langfuse(
    results: dict[str, "EvalResult"],
) -> None:
    """Phase 2: Batch-fetch tool call data from Langfuse for all results.

    Mutates EvalResult objects in place, adding tool_calls and langfuse_trace_id.
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return

    auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)

    async with httpx.AsyncClient(timeout=30) as client:

        async def _lf_get(url: str, **kwargs: Any) -> httpx.Response:
            """GET with retry on 429."""
            for attempt in range(4):
                resp = await client.get(url, auth=auth, **kwargs)
                if resp.status_code != 429:
                    resp.raise_for_status()
                    return resp
                wait = float(resp.headers.get("retry-after", 2 * (attempt + 1)))
                await asyncio.sleep(wait)
            resp.raise_for_status()
            return resp

        for _scenario_id, result in results.items():
            if not result.trace_id:
                continue

            # Throttle between scenarios to avoid 429
            await asyncio.sleep(0.5)

            # Find trace by sessionId
            resp = await _lf_get(
                f"{LANGFUSE_HOST}/api/public/traces",
                params={"sessionId": result.trace_id, "limit": 1},
            )
            traces = resp.json().get("data", [])
            if not traces:
                continue

            lf_trace = traces[0]
            result.langfuse_trace_id = lf_trace.get("id", "")
            observation_ids = lf_trace.get("observations", [])

            # Fetch agent.run observation for tool_calls
            for obs_id in observation_ids:
                await asyncio.sleep(0.3)
                resp = await _lf_get(
                    f"{LANGFUSE_HOST}/api/public/observations/{obs_id}",
                )
                obs = resp.json()

                if obs.get("name") != "agent.run":
                    continue

                output = obs.get("output")
                tool_calls = _extract_tool_calls(output)
                if tool_calls is not None:
                    result.tool_calls = tool_calls
                    break


def _extract_tool_calls(output: Any) -> list[dict[str, Any]] | None:
    """Extract tool_calls_made from an agent.run observation output."""
    if isinstance(output, dict):
        return output.get("tool_calls_made", [])

    # Fallback: parse __state__ from generator output list
    if isinstance(output, list):
        for item in output:
            if (
                isinstance(item, list)
                and len(item) == 2
                and item[0] == "__state__"
                and isinstance(item[1], dict)
            ):
                return item[1].get("tool_calls_made", [])

    return None


async def post_scores_to_langfuse(
    langfuse_trace_id: str,
    scenario_id: str,
    tool_assertion_passed: bool,
    judge_score: float,
    judge_details: list[dict[str, Any]],
) -> None:
    """Post eval scores back to the Langfuse trace for dashboard visibility."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY or not langfuse_trace_id:
        return

    auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{LANGFUSE_HOST}/api/public/scores",
            auth=auth,
            json={
                "traceId": langfuse_trace_id,
                "name": "eval_tool_assertions",
                "value": 1 if tool_assertion_passed else 0,
                "dataType": "BOOLEAN",
                "comment": f"scenario: {scenario_id}",
            },
        )
        await client.post(
            f"{LANGFUSE_HOST}/api/public/scores",
            auth=auth,
            json={
                "traceId": langfuse_trace_id,
                "name": "eval_judge_score",
                "value": judge_score,
                "dataType": "NUMERIC",
                "comment": json.dumps(judge_details[:3]),
            },
        )


class EvalResult:
    def __init__(
        self,
        response: str,
        tool_names_sse: list[str],
        trace_id: str,
        session_id: str,
        tool_calls: list[dict[str, Any]] | None = None,
        langfuse_trace_id: str = "",
    ) -> None:
        self.response = response
        self.all_responses = [response] if response else []
        self.tool_names_sse = tool_names_sse
        self.trace_id = trace_id
        self.session_id = session_id
        self.tool_calls: list[dict[str, Any]] = tool_calls or []
        self.langfuse_trace_id = langfuse_trace_id

    @property
    def tool_names(self) -> list[str]:
        """Tool names from Langfuse (full data) + SSE (fallback for presence)."""
        names = [tc["name"] for tc in self.tool_calls]
        for name in self.tool_names_sse:
            if name not in names:
                names.append(name)
        return names

    def has_tool(self, name: str) -> bool:
        return name in self.tool_names

    def tool_args(self, name: str) -> dict[str, Any] | None:
        """Get args for the first call to this tool, or None."""
        for tc in self.tool_calls:
            if tc["name"] == name:
                return tc["args"]
        return None

    def all_tool_args(self, name: str) -> list[dict[str, Any]]:
        """Get args for all calls to this tool."""
        return [tc["args"] for tc in self.tool_calls if tc["name"] == name]

    def any_tool_arg_contains(self, name: str, key: str, substring: str) -> bool:
        """Case-insensitive substring check on tool args."""
        for tc in self.tool_calls:
            if tc["name"] == name:
                val = tc["args"].get(key)
                if val is not None and substring.lower() in str(val).lower():
                    return True
        return False
