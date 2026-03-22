import json
import uuid
from datetime import datetime
from typing import AsyncGenerator
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.agents.hot_path.graph import app as hot_path_app
from src.agents.hot_path.state import HotPathState
from src.agents.cold_path.extractor import process_brain_dump
from src.core.database import AsyncSessionLocal

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str  # In production, this comes from the auth JWT token
    timezone: str = "UTC"

async def sse_generator(request: ChatRequest) -> AsyncGenerator[dict, None]:
    """Streams the LangGraph execution over SSE."""
    current_time = datetime.now().isoformat()
    
    # 1. Trigger the Cold Path asynchronously (Fire and Forget)
    # In production, this would be an HTTP POST to the QStash webhook endpoint.
    # For now, we spawn it as a background task.
    async def run_cold_path():
        try:
            async with AsyncSessionLocal() as session:
                await process_brain_dump(
                    session=session, 
                    user_id=uuid.UUID(request.user_id), 
                    raw_message=request.message, 
                    current_time_iso=current_time, 
                    timezone=request.timezone
                )
        except Exception as e:
            logger.error(f"Cold Path Failed: {e}")

    import asyncio
    asyncio.create_task(run_cold_path())
    
    # 2. Setup the Hot Path State
    initial_state: HotPathState = {
        "user_id": request.user_id,
        "session_id": request.session_id,
        "messages": [HumanMessage(content=request.message)],
        "iteration": 0,
        "current_time_iso": current_time,
        "timezone": request.timezone,
        "context_string": ""
    }
    
    # 3. Stream LangGraph Events
    # langgraph's astream gives us fine-grained events as nodes execute
    try:
        async for event in hot_path_app.astream(initial_state, stream_mode="updates"):
            # If the LLM generates a response or tool calls
            if "agent" in event:
                for msg in event["agent"]["messages"]:
                    if isinstance(msg, AIMessage):
                        # Clean up the output by hiding the <thought> block from the user UI
                        # (We could also stream tokens here if we used stream_mode="messages")
                        content = msg.content
                        if "<thought>" in content and "</thought>" in content:
                            content = content.split("</thought>")[-1].strip()
                        
                        if content:
                            yield {"event": "message", "data": json.dumps({"content": content})}
                            
                        if msg.tool_calls:
                            yield {"event": "tool_start", "data": json.dumps({"calls": msg.tool_calls})}
                            
            # If a tool finishes executing
            elif "tools" in event:
                for msg in event["tools"]["messages"]:
                    if isinstance(msg, ToolMessage):
                         yield {"event": "tool_end", "data": json.dumps({"name": msg.name, "result": msg.content})}
                         
        # Signal completion
        yield {"event": "done", "data": "[DONE]"}
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield {"event": "error", "data": str(e)}


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """The main endpoint the frontend connects to."""
    return EventSourceResponse(sse_generator(request))
