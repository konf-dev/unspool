"""QStash-authed job router."""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.qstash_auth import verify_qstash_signature
from src.telemetry.logger import get_logger

_log = get_logger("jobs.router")

router = APIRouter(dependencies=[Depends(verify_qstash_signature)])


class ProcessMessageRequest(BaseModel):
    user_id: str
    trace_id: str | None = None
    message: str = ""


class ExecuteActionRequest(BaseModel):
    action_ids: list[str]


class SynthesisRequest(BaseModel):
    user_id: str


@router.post("/synthesis")
async def synthesis(request: SynthesisRequest) -> dict:
    """Run nightly synthesis for a single user. Dispatched by QStash cron."""
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="synthesis", trace_id=trace_id, user_id=request.user_id)

    from src.agents.cold_path.synthesis import run_nightly_synthesis

    try:
        user_uuid = uuid.UUID(request.user_id)
        result = await run_nightly_synthesis(user_uuid)
        _log.info("job.done", job="synthesis", trace_id=trace_id)
        return {"status": "success", "result": result}
    except Exception as e:
        _log.error("synthesis.failed", trace_id=trace_id, exc_info=True)
        return {"status": "failed", "error": str(e)}


@router.post("/hourly-maintenance")
async def hourly_maintenance() -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="hourly_maintenance", trace_id=trace_id)

    results: dict[str, Any] = {}

    from src.jobs.check_deadlines import run_check_deadlines
    from src.jobs.execute_actions import run_execute_actions
    from src.jobs.expire_items import run_expire_items

    for name, fn in [
        ("check_deadlines", run_check_deadlines),
        ("execute_actions", run_execute_actions),
        ("expire_items", run_expire_items),
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

    from src.jobs.reset_notifications import run_reset_notifications
    from src.jobs.detect_patterns import run_detect_patterns

    # Run nightly synthesis for all active users
    from src.db.queries import get_active_users
    from src.agents.cold_path.synthesis import run_nightly_synthesis

    for name, fn in [
        ("reset_notifications", run_reset_notifications),
        ("detect_patterns", run_detect_patterns),
    ]:
        try:
            results[name] = await fn()
        except Exception as e:
            _log.error(f"nightly.{name}_failed", exc_info=True)
            results[name] = {"error": str(e)}

    # Synthesis for all active users
    try:
        users = await get_active_users(days=30)
        synth_count = 0
        for user in users:
            try:
                await run_nightly_synthesis(uuid.UUID(user["id"]))
                synth_count += 1
            except Exception:
                _log.error("nightly.synthesis_user_failed", user_id=user["id"], exc_info=True)
        results["synthesis"] = {"users_processed": synth_count}
    except Exception as e:
        _log.error("nightly.synthesis_failed", exc_info=True)
        results["synthesis"] = {"error": str(e)}

    _log.info("job.done", job="nightly_batch", trace_id=trace_id)
    return results


@router.post("/process-message")
async def process_message(request: ProcessMessageRequest) -> dict:
    trace_id = request.trace_id or str(uuid.uuid4())
    _log.info("job.start", job="process_message", trace_id=trace_id, user_id=request.user_id)

    from src.agents.cold_path.extractor import process_brain_dump

    try:
        await process_brain_dump(
            user_id=uuid.UUID(request.user_id),
            raw_message=request.message,
            current_time_iso=datetime.now(timezone.utc).isoformat(),
            timezone="UTC",
            trace_id=trace_id,
        )
        result = {"status": "processed"}
    except Exception as e:
        _log.error("process_message.failed", exc_info=True)
        result = {"status": "failed", "error": str(e)}

    _log.info("job.done", job="process_message", trace_id=trace_id)
    return result


@router.post("/execute-action")
async def execute_action(request: ExecuteActionRequest) -> dict:
    trace_id = str(uuid.uuid4())
    _log.info("job.start", job="execute_action", trace_id=trace_id, action_ids=request.action_ids)

    from src.jobs.execute_actions import execute_single_action
    from src.db.queries import claim_action

    executed = 0
    failed = 0
    skipped = 0

    for action_id in request.action_ids:
        claimed = await claim_action(action_id)
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
