import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.qstash_auth import verify_qstash_signature
from src.jobs.check_deadlines import run_check_deadlines
from src.jobs.consolidate import run_consolidate
from src.jobs.detect_patterns import run_detect_patterns
from src.jobs.evolve_graph import run_evolve_graph
from src.jobs.execute_actions import run_execute_actions
from src.jobs.expire_items import run_expire_items
from src.jobs.generate_recurrences import run_generate_recurrences
from src.jobs.process_message import run_process_message
from src.jobs.reset_notifications import run_reset_notifications
from src.jobs.summarize_conversations import run_summarize_conversations
from src.jobs.sync_calendar import run_sync_calendar
from src.telemetry.logger import get_logger

_log = get_logger("jobs.router")

router = APIRouter(dependencies=[Depends(verify_qstash_signature)])


class ProcessMessageRequest(BaseModel):
    user_id: str
    message_ids: list[str]
    tool_calls: list[dict[str, Any]] | None = None
    ingest: bool = False
    embeddings: bool = False


# Legacy request model (used by pipeline path)
class ProcessConversationRequest(BaseModel):
    user_id: str
    message_ids: list[str]


@router.post("/check-deadlines")
async def check_deadlines() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="check_deadlines", trace_id=trace_id)
    result = await run_check_deadlines()
    _log.info("job.done", job="check_deadlines", trace_id=trace_id)
    return result


@router.post("/expire-items")
async def expire_items() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="expire_items", trace_id=trace_id)
    result = await run_expire_items()
    _log.info("job.done", job="expire_items", trace_id=trace_id)
    return result


@router.post("/process-message")
async def process_message(request: ProcessMessageRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info(
        "job.start",
        job="process_message",
        trace_id=trace_id,
        user_id=request.user_id,
        ingest=request.ingest,
        embeddings=request.embeddings,
    )
    result = await run_process_message(
        user_id=request.user_id,
        message_ids=request.message_ids,
        tool_calls=request.tool_calls,
        ingest=request.ingest,
        embeddings=request.embeddings,
    )
    _log.info("job.done", job="process_message", trace_id=trace_id)
    return result


@router.post("/sync-calendar")
async def sync_calendar() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="sync_calendar", trace_id=trace_id)
    result = await run_sync_calendar()
    _log.info("job.done", job="sync_calendar", trace_id=trace_id)
    return result


@router.post("/detect-patterns")
async def detect_patterns() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="detect_patterns", trace_id=trace_id)
    result = await run_detect_patterns()
    _log.info("job.done", job="detect_patterns", trace_id=trace_id)
    return result


@router.post("/evolve-graph")
async def evolve_graph() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="evolve_graph", trace_id=trace_id)
    result = await run_evolve_graph()
    _log.info("job.done", job="evolve_graph", trace_id=trace_id)
    return result


@router.post("/summarize")
async def summarize_conversations() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="summarize_conversations", trace_id=trace_id)
    result = await run_summarize_conversations()
    _log.info("job.done", job="summarize_conversations", trace_id=trace_id)
    return result


@router.post("/execute-actions")
async def execute_actions() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="execute_actions", trace_id=trace_id)
    result = await run_execute_actions()
    _log.info("job.done", job="execute_actions", trace_id=trace_id)
    return result


@router.post("/generate-recurrences")
async def generate_recurrences() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="generate_recurrences", trace_id=trace_id)
    result = await run_generate_recurrences()
    _log.info("job.done", job="generate_recurrences", trace_id=trace_id)
    return result


@router.post("/consolidate")
async def consolidate() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="consolidate", trace_id=trace_id)
    result = await run_consolidate()
    _log.info("job.done", job="consolidate", trace_id=trace_id)
    return result


@router.post("/reset-notifications")
async def reset_notifications() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="reset_notifications", trace_id=trace_id)
    result = await run_reset_notifications()
    _log.info("job.done", job="reset_notifications", trace_id=trace_id)
    return result


# Legacy endpoints — forward to process_message for backward compatibility
# These are called by the pipeline path's post_processing dispatch


@router.post("/process-conversation")
async def process_conversation(request: ProcessConversationRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="process_conversation_legacy", trace_id=trace_id)
    result = await run_process_message(
        user_id=request.user_id,
        message_ids=request.message_ids,
        ingest=False,
        embeddings=True,
    )
    _log.info("job.done", job="process_conversation_legacy", trace_id=trace_id)
    return result


@router.post("/process-graph")
async def process_graph(request: ProcessConversationRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="process_graph_legacy", trace_id=trace_id)
    result = await run_process_message(
        user_id=request.user_id,
        message_ids=request.message_ids,
        ingest=True,
        embeddings=False,
    )
    _log.info("job.done", job="process_graph_legacy", trace_id=trace_id)
    return result


@router.post("/decay-urgency")
async def decay_urgency() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="decay_urgency_legacy", trace_id=trace_id)
    result = await run_expire_items()
    _log.info("job.done", job="decay_urgency_legacy", trace_id=trace_id)
    return result
