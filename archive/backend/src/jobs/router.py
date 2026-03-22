import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.qstash_auth import verify_qstash_signature
from src.jobs.check_deadlines import run_check_deadlines
from src.jobs.consolidate import run_consolidate
from src.jobs.detect_patterns import run_detect_patterns
from src.jobs.evolve_graph import run_evolve_graph
from src.jobs.execute_actions import execute_single_action, run_execute_actions
from src.jobs.expire_items import run_expire_items
from src.jobs.generate_recurrences import run_generate_recurrences
from src.jobs.process_message import run_process_message
from src.jobs.reset_notifications import run_reset_notifications
from src.jobs.sync_calendar import run_sync_calendar
from src.db import supabase as db
from src.telemetry.logger import get_logger

_log = get_logger("jobs.router")

router = APIRouter(dependencies=[Depends(verify_qstash_signature)])


class ProcessMessageRequest(BaseModel):
    user_id: str
    message_ids: list[str]
    tool_calls: list[dict[str, Any]] | None = None
    ingest: bool = False
    embeddings: bool = False


class ExecuteActionRequest(BaseModel):
    action_ids: list[str]


# --- Consolidated endpoints (primary targets for cron) ---


@router.post("/hourly-maintenance")
async def hourly_maintenance() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="hourly_maintenance", trace_id=trace_id)

    results: dict[str, Any] = {}
    for name, fn in [
        ("check_deadlines", run_check_deadlines),
        ("execute_actions", run_execute_actions),
        ("expire_items", run_expire_items),
        ("generate_recurrences", run_generate_recurrences),
    ]:
        try:
            results[name] = await fn()
        except Exception as e:
            _log.error(f"hourly.{name}_failed", exc_info=True)
            results[name] = {"error": str(e)}

    _log.info("job.done", job="hourly_maintenance", trace_id=trace_id)
    return results


@router.post("/nightly-batch")
async def nightly_batch() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="nightly_batch", trace_id=trace_id)

    results: dict[str, Any] = {}
    for name, fn in [
        ("reset_notifications", run_reset_notifications),
        ("detect_patterns", run_detect_patterns),
        ("evolve_graph", run_evolve_graph),
        ("consolidate", run_consolidate),
    ]:
        try:
            results[name] = await fn()
        except Exception as e:
            _log.error(f"nightly.{name}_failed", exc_info=True)
            results[name] = {"error": str(e)}

    _log.info("job.done", job="nightly_batch", trace_id=trace_id)
    return results


# --- Targeted dispatch endpoint (for QStash dispatch_at one-shots) ---


@router.post("/execute-action")
async def execute_action(request: ExecuteActionRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info(
        "job.start",
        job="execute_action",
        trace_id=trace_id,
        action_ids=request.action_ids,
    )

    executed = 0
    failed = 0
    skipped = 0

    for action_id in request.action_ids:
        claimed = await db.claim_action(action_id)
        if not claimed:
            skipped += 1
            continue

        result = await execute_single_action(claimed)
        if result == "executed":
            executed += 1
        elif result == "failed":
            failed += 1

    _log.info("job.done", job="execute_action", trace_id=trace_id)
    return {"executed": executed, "failed": failed, "skipped": skipped}


# --- Legacy individual endpoints (kept for in-flight QStash messages) ---


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
