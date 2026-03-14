import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.auth.supabase_auth import get_current_user
from src.db import redis, supabase as db
from src.integrations.qstash import dispatch_job
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
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(..., min_length=1, max_length=100)


async def _check_gate(user_id: str) -> None:
    gate_config = load_config("gate")
    rate_limits = gate_config.get("rate_limits", {})

    tier = "free"
    try:
        cached_tier = await redis.session_get(user_id, "tier")
        if cached_tier:
            tier = cached_tier
        else:
            tier = await db.get_user_tier(user_id)
            await redis.session_set(user_id, "tier", tier)
    except Exception:
        _log.warning("gate.tier_check_failed", user_id=user_id, exc_info=True)

    tier_config = rate_limits.get(tier, rate_limits.get("free", {}))
    daily_limit = tier_config.get("daily_messages", 10)

    if daily_limit < 0:
        return

    try:
        allowed, remaining = await redis.rate_limit_check(user_id, daily_limit)
    except Exception:
        _log.warning("gate.rate_limit_check_failed", user_id=user_id, exc_info=True)
        return  # fail open — let the request through if Redis is down

    if not allowed:
        message = tier_config.get(
            "message",
            "You've reached your daily message limit.",
        )
        raise HTTPException(status_code=429, detail=message)


# Total timeout for the entire chat pipeline (classify + assemble + execute).
# If the LLM hangs or a tool stalls, the user gets an error after this duration.
_PIPELINE_TIMEOUT_SECONDS = 60


async def _stream_response(
    user_id: str,
    message: str,
    trace_id: str,
    context_out: list[Context],
) -> AsyncIterator[str]:
    context = Context(
        user_id=user_id,
        trace_id=trace_id,
        user_message=message,
    )

    async with asyncio.timeout(_PIPELINE_TIMEOUT_SECONDS):
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

    context_out.append(context)

    done_event = json.dumps({"type": "done"})
    yield f"data: {done_event}\n\n"


async def _dispatch_post_processing(
    context: Context,
    user_msg_id: str,
    assistant_msg_id: str,
) -> None:
    if not context.post_processing_jobs:
        return

    try:
        jobs_config = load_config("jobs")
    except FileNotFoundError:
        _log.warning("chat.jobs_config_missing")
        return

    dispatch_map = jobs_config.get("dispatch_map", {})

    for job in context.post_processing_jobs:
        endpoint = dispatch_map.get(job.job, job.job.replace("_", "-"))
        payload = {
            "user_id": context.user_id,
            "trace_id": context.trace_id,
            "message_ids": [user_msg_id, assistant_msg_id],
        }
        await dispatch_job(endpoint, payload, delay=job.delay)


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

    user_msg = await db.save_message(
        user_id=user_id,
        role="user",
        content=request.message,
        metadata={"trace_id": trace_id, "session_id": request.session_id},
    )
    user_msg_id = str(user_msg["id"])

    collected_tokens: list[str] = []
    context_out: list[Context] = []

    async def wrapped_stream() -> AsyncIterator[str]:
        pipeline_failed = False
        try:
            async for chunk in _stream_response(
                user_id, request.message, trace_id, context_out
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
        except TimeoutError:
            pipeline_failed = True
            _log.error(
                "chat.pipeline_timeout",
                trace_id=trace_id,
                user_id=user_id,
                timeout_seconds=_PIPELINE_TIMEOUT_SECONDS,
            )
            error_msg = "sorry, that took too long. try again?"
            error_event = json.dumps({"type": "token", "content": error_msg})
            yield f"data: {error_event}\n\n"
            collected_tokens.append(error_msg)

            done_event = json.dumps({"type": "done"})
            yield f"data: {done_event}\n\n"
        except Exception:
            pipeline_failed = True
            _log.error(
                "chat.pipeline_failed",
                trace_id=trace_id,
                user_id=user_id,
                exc_info=True,
            )
            error_msg = "sorry, something went wrong on my end. try again?"
            error_event = json.dumps({"type": "token", "content": error_msg})
            yield f"data: {error_event}\n\n"
            collected_tokens.append(error_msg)

            done_event = json.dumps({"type": "done"})
            yield f"data: {done_event}\n\n"
        finally:
            # Save and dispatch even if client disconnects mid-stream.
            full_response = "".join(collected_tokens)
            assistant_msg_id = ""
            if full_response:
                try:
                    assistant_msg = await db.save_message(
                        user_id=user_id,
                        role="assistant",
                        content=full_response,
                        metadata={
                            "trace_id": trace_id,
                            "session_id": request.session_id,
                            **({"error": True} if pipeline_failed else {}),
                        },
                    )
                    assistant_msg_id = str(assistant_msg["id"])
                except Exception:
                    _log.error(
                        "chat.save_response_failed",
                        trace_id=trace_id,
                        user_id=user_id,
                        exc_info=True,
                    )

            if context_out and assistant_msg_id and not pipeline_failed:
                await _dispatch_post_processing(
                    context_out[0], user_msg_id, assistant_msg_id
                )

    return StreamingResponse(
        wrapped_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-Id": trace_id,
        },
    )
