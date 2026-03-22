import logging
from typing import Literal
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from src.core.config import settings
from src.agents.hot_path.state import HotPathState
from src.agents.hot_path.tools import query_graph, mutate_graph_status

logger = logging.getLogger(__name__)

# Initialize the LLM for the Hot Path
llm = ChatOpenAI(
    api_key=settings.OPENAI_API_KEY,
    model="gpt-4o", # We use 4o for speed and complex reasoning
    temperature=0.7,
)

# Bind the tools to the LLM
tools = [query_graph, mutate_graph_status]
llm_with_tools = llm.bind_tools(tools)


def _build_system_prompt(state: HotPathState) -> SystemMessage:
    prompt = f"""You are Unspool, a supportive, lightning-fast "second brain" assistant.

Current Time: {state['current_time_iso']}
Timezone: {state['timezone']}
Context: {state['context_string']}

CRITICAL INSTRUCTIONS:
1. You MUST NOT guess node IDs. If a user asks to mark something done, use 'query_graph' first to find the exact ID, then 'mutate_graph_status'.
2. You have a `<thought>` block mandate. If you need to reason about a user's emotional state, figure out which tool to use, or resolve ambiguity, you MUST do it inside a `<thought>...</thought>` XML block at the very start of your message. 
   - Note: The user will never see anything inside the `<thought>` block.
3. Be brief, warm, and avoid conversational filler outside of the thought block.

Example:
User: "I finished the thesis"
You: <thought>I need to find the node ID for 'thesis' before I can mark it done.</thought>
[Tool Call: query_graph("thesis")]
"""
    return SystemMessage(content=prompt)


async def call_model(state: HotPathState):
    """The main LLM execution node."""
    logger.info(f"HotPath Iteration: {state['iteration']}")
    
    messages = state["messages"]
    
    # We inject the dynamic system prompt at the beginning of the context
    system_message = _build_system_prompt(state)
    
    # Check if we need to forcefully inject the user_id into tool calls
    # Langchain tools can be tricky with injected state, so we handle it here if needed,
    # but currently our tools require `user_id` as an argument. We must ensure the LLM knows it.
    
    # We append the user_id to the system prompt so the LLM knows what to pass to tools
    system_message.content += f"\n\nYour user_id is: {state['user_id']}. ALWAYS pass this to your tools."
    
    full_messages = [system_message] + messages
    
    response = await llm_with_tools.ainvoke(full_messages)
    
    return {"messages": [response], "iteration": state["iteration"] + 1}


async def call_tools(state: HotPathState):
    """Executes the tools requested by the LLM."""
    last_message = state["messages"][-1]
    
    tool_responses = []
    
    # Note: In a production LangGraph app, you usually use ToolNode.
    # We are manually unpacking here for absolute control over async DB sessions and errors.
    for tool_call in last_message.tool_calls:
        logger.info(f"Executing tool: {tool_call['name']}")
        try:
            if tool_call["name"] == "query_graph":
                result = await query_graph.ainvoke(tool_call["args"])
            elif tool_call["name"] == "mutate_graph_status":
                result = await mutate_graph_status.ainvoke(tool_call["args"])
            else:
                result = f"Unknown tool: {tool_call['name']}"
                
            tool_responses.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_call["name"]
            ))
            
        except Exception as e:
            logger.error(f"Tool {tool_call['name']} failed: {e}")
            tool_responses.append(ToolMessage(
                content=f"Error: {str(e)}",
                tool_call_id=tool_call["id"],
                name=tool_call["name"]
            ))
            
    return {"messages": tool_responses}


def route_logic(state: HotPathState) -> Literal["tools", "END"]:
    """Determines whether to execute tools or end the loop."""
    last_message = state["messages"][-1]
    
    # If the LLM returned tool calls, go to the tools node
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"
        
    # If we've looped too many times, force an end to prevent infinite loops
    if state["iteration"] > 5:
        logger.warning("HotPath reached iteration limit. Forcing exit.")
        return "END"
        
    return "END"


# Build the Graph
workflow = StateGraph(HotPathState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    route_logic,
    {
        "tools": "tools",
        "END": END
    }
)
workflow.add_edge("tools", "agent")

app = workflow.compile()
