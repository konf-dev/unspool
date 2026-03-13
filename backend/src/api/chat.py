import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.auth.supabase_auth import get_current_user
from src.db import redis, supabase as db
from src.orchestrator.config_loader import load_config
from src.orchestrator.context import assemble_context
from src.orchestrator.engine import execute_pipeline
from src.orchestrator.intent import classify_intent
from src.orchestrator.types import Context
from src.telemetry.logger import get_logger
from src.tools.registry import get_tool_registry

_log = get_logger("api.chat")

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str


async def _check_gate(user_id: str) -> None:
    gate_config = load_config("gate")
    rate_limits = gate_config.get("rate_limits", {})

    cached_tier = await redis.session_get(user_id, "tier")
    if cached_tier:
        tier = cached_tier
    else:
        tier = await db.get_user_tier(user_id)
        await redis.session_set(user_id, "tier", tier)

    tier_config = rate_limits.get(tier, rate_limits.get("free", {}))
    daily_limit = tier_config.get("daily_messages", 10)

    if daily_limit < 0:
        return

    allowed, remaining = await redis.rate_limit_check(user_id, daily_limit)
    if not allowed:
        message = tier_config.get(
            "message",
            "You've reached your daily message limit.",
        )
        raise HTTPException(status_code=429, detail=message)


async def _stream_response(
    user_id: str,
    message: str,
    trace_id: str,
) -> AsyncIterator[str]:
    context = Context(
        user_id=user_id,
        trace_id=trace_id,
        user_message=message,
    )
    intent_name, pipeline_name, confidence = await classify_intent(message, context)

    context = await assemble_context(user_id, trace_id, message, intent_name)

    _log.info(
        "chat.pipeline_start",
        trace_id=trace_id,
        intent=intent_name,
        pipeline=pipeline_name,
        confidence=confidence,
    )

    tool_registry = get_tool_registry()

    async for token in execute_pipeline(pipeline_name, context, tool_registry):
        event = json.dumps({"type": "token", "content": token})
        yield f"data: {event}\n\n"

    done_event = json.dumps({"type": "done"})
    yield f"data: {done_event}\n\n"


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

    await _check_gate(user_id)

    await db.save_message(
        user_id=user_id,
        role="user",
        content=request.message,
        metadata={"trace_id": trace_id, "session_id": request.session_id},
    )

    collected_tokens: list[str] = []

    async def wrapped_stream() -> AsyncIterator[str]:
        async for chunk in _stream_response(user_id, request.message, trace_id):
            if '"type": "token"' in chunk:
                try:
                    data_str = chunk.removeprefix("data: ").strip()
                    parsed = json.loads(data_str)
                    if parsed.get("type") == "token":
                        collected_tokens.append(parsed["content"])
                except (json.JSONDecodeError, KeyError):
                    pass
            yield chunk

        full_response = "".join(collected_tokens)
        if full_response:
            try:
                await db.save_message(
                    user_id=user_id,
                    role="assistant",
                    content=full_response,
                    metadata={"trace_id": trace_id, "session_id": request.session_id},
                )
            except Exception:
                _log.error(
                    "chat.save_response_failed",
                    trace_id=trace_id,
                    user_id=user_id,
                    exc_info=True,
                )

        _log.info("chat.post_processing_scheduled", trace_id=trace_id)

    return StreamingResponse(
        wrapped_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-Id": trace_id,
        },
    )
