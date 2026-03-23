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
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from src.agents.hot_path.state import HotPathState
from src.agents.hot_path.system_prompt import build_system_prompt
from src.agents.hot_path.tools import (
    query_graph,
    mutate_graph,
    _exec_query_graph,
    _exec_mutate_graph,
)
from src.db.queries import save_llm_usage
from src.telemetry.logger import get_logger

logger = get_logger("hot_path.graph")

_llm_with_tools: ChatOpenAI | None = None


def _get_llm_with_tools() -> ChatOpenAI:
    """Lazy-init the LLM + tool binding so nothing runs at import time."""
    global _llm_with_tools
    if _llm_with_tools is None:
        from src.core.settings import get_settings
        settings = get_settings()
        llm = ChatOpenAI(
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY,
            model=settings.LLM_MODEL,
            temperature=0.7,
        )
        _llm_with_tools = llm.bind_tools([query_graph, mutate_graph])
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
            model=get_settings().LLM_MODEL,
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
                result = await _exec_query_graph(
                    user_id=user_id,
                    semantic_query=args.get("semantic_query", ""),
                    edge_type_filter=args.get("edge_type_filter"),
                    node_type=args.get("node_type"),
                )
            elif tool_call["name"] == "mutate_graph":
                args = tool_call["args"]
                result = await _exec_mutate_graph(
                    user_id=user_id,
                    action=args.get("action", ""),
                    node_id=args.get("node_id", ""),
                    value=args.get("value"),
                    target_node_id=args.get("target_node_id"),
                    edge_type=args.get("edge_type"),
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
    if state["iteration"] >= 5:
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


def get_langfuse_config(
    trace_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build a LangGraph config dict with Langfuse CallbackHandler if available.

    Usage in chat.py::

        config = get_langfuse_config(trace_id, user_id, session_id)
        async for event in app.astream(state, stream_mode="updates", config=config):
            ...
    """
    from src.telemetry.langfuse_integration import get_langchain_handler
    handler = get_langchain_handler(
        trace_id=trace_id,
        user_id=user_id,
        session_id=session_id,
        tags=["chat", "hot_path"],
        metadata={"trace_id": trace_id} if trace_id else {},
    )
    if handler:
        return {"callbacks": [handler]}
    return {}
