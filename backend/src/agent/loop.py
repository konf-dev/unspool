import json
from collections.abc import AsyncIterator
from typing import Any

from src.agent.context import assemble_context
from src.agent.streaming import format_sse_event
from src.agent.system_prompt import build_system_prompt
from src.agent.tools import execute_tool, get_tool_definitions
from src.agent.types import AgentState, ToolCall
from src.llm.registry import get_llm_provider
from src.telemetry.langfuse_integration import observe, update_current_observation
from src.telemetry.logger import get_logger

_log = get_logger("agent.loop")

MAX_ROUNDS = 5


@observe("tool.execute")
async def _execute_tool_observed(
    name: str, args: dict[str, Any], user_id: str, state: AgentState
) -> Any:
    """Wraps execute_tool so each call appears as a Langfuse span."""
    update_current_observation(
        input={"tool": name, "args": args},
    )
    result = await execute_tool(name, args, user_id, state)
    update_current_observation(
        output={"result": result.output, "is_error": result.is_error},
    )
    return result


@observe("agent.run")
async def run_agent(
    user_id: str,
    message: str,
    trace_id: str,
) -> AsyncIterator[tuple[str, AgentState]]:
    """Run the agent loop. Yields SSE-formatted strings.

    Returns the AgentState via the final yield as a tuple ("__state__", state).
    All other yields are ("sse", sse_string).
    """
    state = AgentState(user_id=user_id, trace_id=trace_id, user_message=message)

    # 1. Assemble context
    context_block, profile, recent_messages = await assemble_context(
        user_id, message, trace_id
    )

    # 2. Build system prompt
    system_prompt = build_system_prompt(profile, context_block)

    # 3. Build message array
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in recent_messages[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": f"<user_input>{message}</user_input>",
        }
    )

    # 4. Tool definitions
    tools = get_tool_definitions()

    # 5. Agent loop
    provider = get_llm_provider()

    for _round in range(MAX_ROUNDS):
        pending_calls: dict[str, ToolCall] = {}
        text_chunks: list[str] = []
        has_tool_calls = False

        async for event in provider.stream_with_tools(messages, tools):
            if event.type == "text_delta":
                yield ("sse", format_sse_event("token", content=event.content))
                text_chunks.append(event.content)

            elif event.type == "tool_call_start":
                has_tool_calls = True
                pending_calls[event.tool_call_id] = ToolCall(
                    id=event.tool_call_id,
                    name=event.tool_name,
                    arguments="",
                )

            elif event.type == "tool_call_delta":
                tc = pending_calls.get(event.tool_call_id)
                if tc:
                    tc.arguments += event.arguments_delta

            elif event.type == "tool_call_done":
                tc = pending_calls.get(event.tool_call_id)
                if tc:
                    tc.arguments = event.arguments_delta

            elif event.type == "done":
                state.total_input_tokens += event.input_tokens
                state.total_output_tokens += event.output_tokens

        if text_chunks:
            state.response_text += "".join(text_chunks)

        if not has_tool_calls:
            break

        # Execute tool calls and build messages for next round
        assistant_tool_calls = []
        tool_result_messages = []

        for tc in pending_calls.values():
            yield (
                "sse",
                format_sse_event("tool_status", tool=tc.name, status="running"),
            )

            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                args = {}
                _log.warning(
                    "agent.tool_args_parse_failed", tool=tc.name, trace_id=trace_id
                )

            result = await _execute_tool_observed(tc.name, args, user_id, state)
            result.tool_call_id = tc.id

            state.tool_calls_made.append(
                {
                    "name": tc.name,
                    "args": args,
                    "result": result.output,
                    "is_error": result.is_error,
                }
            )

            assistant_tool_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
            )

            tool_result_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.output,
                }
            )

            yield ("sse", format_sse_event("tool_status", tool=tc.name, status="done"))

        # Add assistant message with tool calls
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": assistant_tool_calls,
        }
        if text_chunks:
            assistant_msg["content"] = "".join(text_chunks)
        messages.append(assistant_msg)

        # Add tool results
        messages.extend(tool_result_messages)

        # Reset for next round
        text_chunks = []

    update_current_observation(
        input={"user_message": message, "message_count": len(messages)},
        output={
            "response_text": state.response_text,
            "tool_calls_made": state.tool_calls_made,
        },
        usage={
            "input": state.total_input_tokens,
            "output": state.total_output_tokens,
        },
    )

    yield ("sse", format_sse_event("done"))
    yield ("__state__", state)  # type: ignore[misc]
