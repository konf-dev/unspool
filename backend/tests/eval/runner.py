"""Eval runner: executes the agent loop with controlled context and mocked tools."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

from src.agent.loop import run_agent
from src.agent.types import ToolResult


# Plausible tool results for eval — the agent should respond well regardless
_TOOL_RESULTS: dict[str, Any] = {
    "save_items": {"saved": True, "count": 0},  # count set dynamically
    "mark_done": {"marked": True, "item": "task"},
    "pick_next": {
        "item": {
            "interpreted_action": "Email prof about extension",
            "energy_estimate": "low",
            "deadline_at": None,
            "raw_text": "email prof about extension",
        }
    },
    "search": {"results": [], "count": 0},
    "get_upcoming": {"items": [], "events": []},
    "get_progress": {"done_today": 2, "done_this_week": 8, "open": 12},
    "update_item": {"updated": True},
    "remove_item": {"removed": True},
    "save_preference": {"saved": True},
    "decompose_task": {"steps": ["step 1", "step 2", "step 3"]},
    "remember": {"noted": True},
    "save_event": {"saved": True, "event_id": "evt-123"},
    "log_entry": {"logged": True},
    "get_tracker_summary": {"entries": [], "summary": "no data yet"},
    "save_note": {"saved": True},
    "schedule_action": {"scheduled": True},
    "manage_collection": {"ok": True},
}


def _make_tool_handler(tool_results: dict[str, Any] | None = None) -> AsyncMock:
    results = {**_TOOL_RESULTS, **(tool_results or {})}

    async def _handler(
        name: str, args: dict[str, Any], user_id: str, state: Any
    ) -> ToolResult:
        result = results.get(name, {"ok": True})

        # Dynamic: save_items count
        if name == "save_items" and "items" in args:
            result = {**result, "count": len(args["items"])}

        return ToolResult(
            tool_call_id="",
            name=name,
            output=json.dumps(result),
        )

    mock = AsyncMock(side_effect=_handler)
    return mock


async def run_eval_scenario(
    conversation: list[dict[str, str]],
    context_block: str = "",
    profile: dict[str, Any] | None = None,
    tool_results: dict[str, Any] | None = None,
    seed_messages: list[dict[str, Any]] | None = None,
) -> "EvalResult":
    """Run the agent loop for an eval scenario.

    Args:
        conversation: List of {"role": "user", "content": "..."} messages.
            Multi-turn: runs the agent for each user message sequentially.
        context_block: Pre-built <context> block for the system prompt.
        profile: User profile dict (tone, timezone, etc).
        tool_results: Override default tool results for specific tools.
        seed_messages: Pre-existing conversation history.

    Returns:
        EvalResult with response text, tool calls, and metadata.
    """
    default_profile: dict[str, Any] = {
        "timezone": "America/New_York",
        "tone_preference": "casual",
        "length_preference": "medium",
        "pushiness_preference": "gentle",
        "uses_emoji": False,
        "primary_language": "en",
        "display_name": "Test User",
    }
    merged_profile = {**default_profile, **(profile or {})}
    history = list(seed_messages or [])
    user_id = f"eval-{uuid.uuid4().hex[:8]}"
    trace_id = f"eval-{uuid.uuid4().hex[:12]}"

    tool_handler = _make_tool_handler(tool_results)
    all_responses: list[str] = []
    all_tool_calls: list[dict[str, Any]] = []

    for turn in conversation:
        if turn["role"] != "user":
            continue

        mock_context = AsyncMock(return_value=(context_block, merged_profile, history))

        with (
            patch("src.agent.loop.assemble_context", mock_context),
            patch("src.agent.loop.execute_tool", tool_handler),
        ):
            response_text = ""
            tool_calls: list[dict[str, Any]] = []

            async for tag, payload in run_agent(user_id, turn["content"], trace_id):
                if tag == "sse":
                    pass  # SSE events not needed for eval
                elif tag == "__state__":
                    response_text = payload.response_text
                    tool_calls = payload.tool_calls_made

        all_responses.append(response_text)
        all_tool_calls.extend(tool_calls)

        # Add to history for multi-turn
        history.append({"role": "user", "content": turn["content"]})
        history.append({"role": "assistant", "content": response_text})

    return EvalResult(
        response=all_responses[-1] if all_responses else "",
        all_responses=all_responses,
        tool_calls=all_tool_calls,
        user_id=user_id,
        trace_id=trace_id,
    )


class EvalResult:
    def __init__(
        self,
        response: str,
        all_responses: list[str],
        tool_calls: list[dict[str, Any]],
        user_id: str,
        trace_id: str,
    ) -> None:
        self.response = response
        self.all_responses = all_responses
        self.tool_calls = tool_calls
        self.user_id = user_id
        self.trace_id = trace_id

    @property
    def tool_names(self) -> list[str]:
        return [tc["name"] for tc in self.tool_calls]

    def has_tool(self, name: str) -> bool:
        return name in self.tool_names
