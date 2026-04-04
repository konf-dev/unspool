"""LangGraph workflow for the hot path conversational agent.

The LLM and workflow are constructed lazily on first use to avoid import-time
side effects (which break tests and fail when env vars are missing).

Langfuse tracing is done via CallbackHandler passed in the config dict — this
automatically traces every LLM call, tool execution, and agent iteration with
full input/output/token counts.
"""

import time
from typing import Any, Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

from src.agents.hot_path.state import HotPathState
from src.agents.hot_path.system_prompt import build_system_prompt
from src.agents.hot_path.tools import (
    query_graph,
    mutate_graph,
    schedule_reminder,
    get_metrics,
    _exec_query_graph,
    _exec_mutate_graph,
    _exec_schedule_reminder,
    _exec_get_metrics,
)
from src.db.queries import save_llm_usage
from src.telemetry.logger import get_logger

logger = get_logger("hot_path.graph")

_llm_with_tools: ChatGoogleGenerativeAI | None = None


def _get_llm_with_tools() -> ChatGoogleGenerativeAI:
    """Lazy-init the LLM + tool binding so nothing runs at import time."""
    global _llm_with_tools
    if _llm_with_tools is None:
        from src.core.settings import get_settings
        settings = get_settings()
        from src.core.config_loader import hp
        llm = ChatGoogleGenerativeAI(
            google_api_key=settings.api_key_for(settings.CHAT_PROVIDER),
            model=settings.CHAT_MODEL,
            temperature=hp("agent", "llm_temperature", 0.4),
            thinking_budget=hp("agent", "llm_thinking_budget", 4096),
        )
        _llm_with_tools = llm.bind_tools([query_graph, mutate_graph, schedule_reminder, get_metrics])
    return _llm_with_tools


async def call_model(state: HotPathState):
    """The main LLM execution node."""
    logger.info("hot_path.iteration", iteration=state["iteration"])

    system_prompt = build_system_prompt(
        profile=state.get("profile"),
        context_block=state.get("context_string", ""),
    )

    full_messages = [SystemMessage(content=system_prompt)] + state["messages"]

    start = time.perf_counter()
    response = await _get_llm_with_tools().ainvoke(full_messages)
    latency_ms = round((time.perf_counter() - start) * 1000)

    # Record LLM usage to our DB (Langfuse records it too via CallbackHandler)
    usage = getattr(response, "usage_metadata", None) or {}
    try:
        from src.core.settings import get_settings
        await save_llm_usage(
            pipeline="hot_path",
            model=get_settings().CHAT_MODEL,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency_ms,
            trace_id=state.get("trace_id"),
            user_id=state.get("user_id"),
        )
    except Exception:
        logger.debug("hot_path.usage_tracking_failed", exc_info=True)

    return {"messages": [response], "iteration": state["iteration"] + 1}


async def call_tools(state: HotPathState):
    """Executes tools with user_id injected from state — LLM never sees user_id."""
    last_message = state["messages"][-1]
    user_id = state["user_id"]

    tool_responses = []

    for tool_call in last_message.tool_calls:
        logger.info("hot_path.tool_call", tool=tool_call["name"])
        try:
            if tool_call["name"] == "query_graph":
                args = tool_call["args"]
                semantic_query = args.get("semantic_query")
                edge_type_filter = args.get("edge_type_filter")
                node_type = args.get("node_type")
                date_from = args.get("date_from")
                date_to = args.get("date_to")
                # At least one filter must be provided
                sq = str(semantic_query).strip() if semantic_query else None
                if not sq and not edge_type_filter and not node_type:
                    result = (
                        "Error: provide at least one of semantic_query, "
                        "edge_type_filter, or node_type."
                    )
                else:
                    result = await _exec_query_graph(
                        user_id=user_id,
                        semantic_query=sq,
                        edge_type_filter=edge_type_filter,
                        node_type=node_type,
                        date_from=date_from,
                        date_to=date_to,
                        depth=int(args.get("depth", 0)),
                    )
            elif tool_call["name"] == "mutate_graph":
                args = tool_call["args"]
                action = args.get("action")
                node_id = args.get("node_id")
                missing = []
                if not action or not str(action).strip():
                    missing.append("action")
                if not node_id or not str(node_id).strip():
                    missing.append("node_id")
                if missing:
                    result = (
                        f"Error: required parameter(s) missing: {', '.join(missing)}. "
                        "Use query_graph first to find node IDs."
                    )
                else:
                    result = await _exec_mutate_graph(
                        user_id=user_id,
                        action=str(action).strip(),
                        node_id=str(node_id).strip(),
                        value=args.get("value"),
                        target_node_id=args.get("target_node_id"),
                        edge_type=args.get("edge_type"),
                    )
            elif tool_call["name"] == "schedule_reminder":
                args = tool_call["args"]
                reminder_text = args.get("reminder_text", "")
                remind_at = args.get("remind_at", "")
                if not reminder_text or not remind_at:
                    result = "Error: both reminder_text and remind_at are required."
                else:
                    result = await _exec_schedule_reminder(
                        user_id=user_id,
                        reminder_text=str(reminder_text).strip(),
                        remind_at=str(remind_at).strip(),
                    )
            elif tool_call["name"] == "get_metrics":
                args = tool_call["args"]
                result = await _exec_get_metrics(
                    user_id=user_id,
                    metric_name=args.get("metric_name"),
                    date_from=args.get("date_from"),
                    date_to=args.get("date_to"),
                )
            else:
                result = f"Unknown tool: {tool_call['name']}"

            tool_responses.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            ))

        except Exception as e:
            logger.error("hot_path.tool_failed", tool=tool_call["name"], error=str(e))
            tool_responses.append(ToolMessage(
                content=f"Error: {str(e)}",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            ))

    return {"messages": tool_responses}


def route_logic(state: HotPathState) -> Literal["tools", "END"]:
    """Determines whether to execute tools or end the loop."""
    from src.core.config_loader import hp
    if state["iteration"] >= int(hp("agent", "max_iterations", 5)):
        logger.warning("hot_path.iteration_limit_reached")
        return "END"

    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"

    return "END"


# Build the Graph
workflow = StateGraph(HotPathState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    route_logic,
    {"tools": "tools", "END": END},
)
workflow.add_edge("tools", "agent")

app = workflow.compile()
