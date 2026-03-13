import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.qstash_auth import verify_qstash_signature
from src.jobs.check_deadlines import run_check_deadlines
from src.jobs.decay_urgency import run_decay_urgency
from src.jobs.detect_patterns import run_detect_patterns
from src.jobs.process_conversation import run_process_conversation
from src.jobs.sync_calendar import run_sync_calendar
from src.telemetry.logger import get_logger

_log = get_logger("jobs.router")

router = APIRouter(dependencies=[Depends(verify_qstash_signature)])


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


@router.post("/decay-urgency")
async def decay_urgency() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="decay_urgency", trace_id=trace_id)
    result = await run_decay_urgency()
    _log.info("job.done", job="decay_urgency", trace_id=trace_id)
    return result


@router.post("/process-conversation")
async def process_conversation(request: ProcessConversationRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="process_conversation", trace_id=trace_id, user_id=request.user_id)
    result = await run_process_conversation(request.user_id, request.message_ids)
    _log.info("job.done", job="process_conversation", trace_id=trace_id)
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
