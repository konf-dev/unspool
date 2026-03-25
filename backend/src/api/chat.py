"""Main chat streaming endpoint — full rewrite with auth, context, event persistence."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from src.agents.hot_path.context import assemble_context
from src.agents.hot_path.graph import app as hot_path_app
from src.agents.hot_path.state import HotPathState
from src.api.gate import check_gate
from src.auth.supabase_auth import get_current_user
from src.core.database import AsyncSessionLocal
from src.db.queries import append_message_event, update_profile
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import (
    observe,
    propagate_trace_attributes,
    get_langchain_handler_from_context,
    flush_langfuse,
)
from src.telemetry.logger import get_logger

_log = get_logger("api.chat")

router = APIRouter()

_PIPELINE_TIMEOUT_SECONDS = 60


def _token_event(text: str) -> str:
    return f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"


def _update_thought_state(text: str, in_thought: bool) -> bool:
    """Compute the final in_thought state after processing a chunk."""
    while "<thought>" in text or "</thought>" in text:
        if "<thought>" in text:
            _, _, text = text.partition("<thought>")
            in_thought = True
        if "</thought>" in text:
            _, _, text = text.partition("</thought>")
            in_thought = False
    return in_thought


async def _filter_thoughts(text: str, in_thought: bool):
    """Yield token events for visible text, filtering out <thought> blocks.

    Handles: both tags in one chunk, split across chunks, multiple blocks.
    """
    while "<thought>" in text or "</thought>" in text:
        if "<thought>" in text:
            before, _, rest = text.partition("<thought>")
            if before and not in_thought:
                yield _token_event(before)
            in_thought = True
            text = rest
        if "</thought>" in text:
            _, _, after = text.partition("</thought>")
            in_thought = False
            text = after
    if text and not in_thought:
        yield _token_event(text)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(..., min_length=1, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)


@observe(name="chat")
async def _stream_response(
    user_id: str,
    message: str,
    trace_id: str,
    context_block: str,
    profile: dict[str, Any],
    recent_messages: list[dict[str, Any]],
    session_id: str,
    tz: str,
) -> AsyncIterator[str]:
    # Set trace-level attributes (user_id, session_id, tags) on this trace
    # Note: propagate_attributes returns a sync context manager (_AgnosticContextManager)
    with propagate_trace_attributes(
        user_id=user_id,
        session_id=session_id,
        tags=["chat"],
    ):
        current_time = datetime.now(timezone.utc).isoformat()

        # Build conversation history from recent messages
        history_messages = []
        for msg in recent_messages[-10:]:
            if msg.get("role") == "user":
                history_messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                history_messages.append(AIMessage(content=msg.get("content", "")))

        initial_state: HotPathState = {
            "user_id": user_id,
            "session_id": session_id,
            "messages": history_messages + [HumanMessage(content=message)],
            "iteration": 0,
            "current_time_iso": current_time,
            "timezone": tz or "UTC",
            "context_string": context_block,
            "trace_id": trace_id,
            "profile": profile,
        }

        # LangChain CallbackHandler inherits current @observe trace context
        handler = get_langchain_handler_from_context()
        langfuse_config = {"callbacks": [handler]} if handler else {}

        in_thought = False  # Track whether we're inside a <thought> block

        async with asyncio.timeout(_PIPELINE_TIMEOUT_SECONDS):
            async for event in hot_path_app.astream_events(
                initial_state, version="v2", config=langfuse_config,
            ):
                kind = event.get("event", "")

                # Token-by-token streaming from the LLM
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        # Gemini thinking blocks come as list items
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict):
                                    text = block.get("text", "")
                                else:
                                    text = str(block)
                                if text:
                                    async for evt in _filter_thoughts(text, in_thought):
                                        yield evt
                                    in_thought = _update_thought_state(text, in_thought)
                        elif isinstance(content, str) and content:
                            async for evt in _filter_thoughts(content, in_thought):
                                yield evt
                            in_thought = _update_thought_state(content, in_thought)

                        # Tool calls from the LLM
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            yield f"data: {json.dumps({'type': 'tool_start', 'calls': [tc['name'] for tc in chunk.tool_calls]})}\n\n"

                # Tool execution completed
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name:
                        yield f"data: {json.dumps({'type': 'tool_end', 'name': tool_name})}\n\n"

            # Send plate data inline before done to avoid race condition
            try:
                from src.db.queries import get_plate_items
                plate_items = await get_plate_items(user_id)
                if plate_items:
                    plate_data = [
                        {
                            "id": str(p["node_id"]),
                            "content": p["content"],
                            "deadline": str(p["deadline"]) if p.get("deadline") else None,
                        }
                        for p in plate_items
                    ]
                    yield f"data: {json.dumps({'type': 'plate', 'items': plate_data})}\n\n"
            except Exception:
                pass  # Plate failure should never block done

            yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    trace_id = str(uuid.uuid4())

    _log.info(
        "chat.request",
        trace_id=trace_id,
        user_id=user_id,
        session_id=request.session_id,
    )

    await check_gate(user_id)

    # Sync browser timezone to profile
    if request.timezone:
        try:
            await update_profile(user_id, timezone=request.timezone)
        except Exception as e:
            report_error("chat.timezone_sync_failed", e, user_id=user_id)

    # Persist user message as event
    async with AsyncSessionLocal() as session:
        user_event = await append_message_event(
            session, user_id, "user", request.message,
            metadata={"trace_id": trace_id, "session_id": request.session_id},
        )
        await session.commit()

    # Assemble context in parallel
    context_block, profile, recent_messages = await assemble_context(
        user_id, request.message, trace_id,
    )

    # Update last interaction
    try:
        await update_profile(user_id, last_interaction_at=datetime.now(timezone.utc))
    except Exception:
        pass

    collected_tokens: list[str] = []
    stream_state: dict[str, bool] = {"failed": False, "completed": False}

    async def wrapped_stream() -> AsyncIterator[str]:
        try:
            try:
                async for chunk in _stream_response(
                    user_id=user_id,
                    message=request.message,
                    trace_id=trace_id,
                    context_block=context_block,
                    profile=profile,
                    recent_messages=recent_messages,
                    session_id=request.session_id,
                    tz=request.timezone or "UTC",
                ):
                    if '"type": "token"' in chunk:
                        try:
                            data_str = chunk.removeprefix("data: ").strip()
                            parsed = json.loads(data_str)
                            if parsed.get("type") == "token":
                                collected_tokens.append(parsed["content"])
                        except (json.JSONDecodeError, KeyError):
                            pass
                    yield chunk
                stream_state["completed"] = True
            except TimeoutError:
                stream_state["failed"] = True
                _log.error("chat.pipeline_timeout", trace_id=trace_id, user_id=user_id)
                error_msg = "sorry, that took too long. try again?"
                yield f"data: {json.dumps({'type': 'token', 'content': error_msg})}\n\n"
                collected_tokens.append(error_msg)
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception:
                stream_state["failed"] = True
                _log.error("chat.pipeline_failed", trace_id=trace_id, user_id=user_id, exc_info=True)
                error_msg = "sorry, something went wrong on my end. try again?"
                yield f"data: {json.dumps({'type': 'token', 'content': error_msg})}\n\n"
                collected_tokens.append(error_msg)
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            # Save assistant response as event
            full_response = "".join(collected_tokens)
            if full_response:
                metadata: dict[str, Any] = {"trace_id": trace_id, "session_id": request.session_id}
                if stream_state.get("failed"):
                    metadata["error"] = True
                if not stream_state.get("completed"):
                    metadata["partial"] = True

                try:
                    from src.db.queries import get_plate_items
                    plate_items = await get_plate_items(user_id)
                    metadata["plate"] = {
                        "items": [
                            {
                                "id": str(p["node_id"]),
                                "content": p["content"],
                                "deadline": str(p["deadline"]) if p.get("deadline") else None,
                                "created_at": str(p["created_at"]) if p.get("created_at") else None,
                            }
                            for p in plate_items
                        ]
                    }
                except Exception:
                    pass  # Plate failure should never break chat

                try:
                    async with AsyncSessionLocal() as session:
                        await append_message_event(
                            session, user_id, "assistant", full_response, metadata,
                        )
                        await session.commit()
                except Exception:
                    _log.error("chat.save_response_failed", trace_id=trace_id, exc_info=True)

                # Dispatch cold path via QStash (not asyncio.create_task)
                if stream_state.get("completed") and not stream_state.get("failed"):
                    try:
                        from src.integrations.qstash import dispatch_job
                        await dispatch_job("process-message", {
                            "user_id": user_id,
                            "trace_id": trace_id,
                            "message": request.message,
                        }, delay=5)
                    except Exception:
                        _log.error("chat.cold_path_dispatch_failed", trace_id=trace_id, exc_info=True)

                # Flush Langfuse so the trace is sent before connection closes
                flush_langfuse()

    return StreamingResponse(
        wrapped_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-Id": trace_id,
        },
    )
