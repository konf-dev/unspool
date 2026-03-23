from datetime import datetime
from typing import Any

from qstash import AsyncQStash

from src.core.settings import get_settings
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

_log = get_logger("integrations.qstash")
_client: AsyncQStash | None = None


def _get_client() -> AsyncQStash:
    global _client
    if _client is None:
        settings = get_settings()
        kwargs: dict = {"token": settings.QSTASH_TOKEN}
        if settings.QSTASH_URL:
            kwargs["base_url"] = settings.QSTASH_URL
        _client = AsyncQStash(**kwargs)
    return _client


def _build_url(endpoint: str) -> str:
    settings = get_settings()
    base = settings.API_URL.rstrip("/")
    return f"{base}/jobs/{endpoint}"


async def dispatch_job(
    endpoint: str,
    payload: dict[str, Any],
    delay: str | int = 0,
) -> str | None:
    url = _build_url(endpoint)
    try:
        client = _get_client()
        response = await client.message.publish_json(
            url=url, body=payload, delay=delay if delay else None,
        )
        msg_id = str(getattr(response, "message_id", None) or response)
        _log.info("qstash.dispatched", endpoint=endpoint, delay=delay, message_id=msg_id)
        return msg_id
    except Exception as exc:
        report_error("qstash.dispatch_failed", exc, endpoint=endpoint)
        return None


async def schedule_cron(
    endpoint: str,
    cron_expression: str,
    schedule_id: str | None = None,
) -> str | None:
    url = _build_url(endpoint)
    try:
        client = _get_client()
        sid = await client.schedule.create(
            destination=url, cron=cron_expression, schedule_id=schedule_id,
        )
        _log.info("qstash.cron_registered", endpoint=endpoint, cron=cron_expression, schedule_id=sid)
        return sid
    except Exception as exc:
        report_error("qstash.cron_registration_failed", exc, endpoint=endpoint)
        return None


async def dispatch_at(
    endpoint: str,
    payload: dict[str, Any],
    deliver_at: datetime,
) -> str | None:
    if deliver_at.tzinfo is None:
        raise ValueError("deliver_at must be timezone-aware")
    url = _build_url(endpoint)
    not_before = int(deliver_at.timestamp())
    try:
        client = _get_client()
        response = await client.message.publish_json(
            url=url, body=payload, not_before=not_before,
        )
        msg_id = str(getattr(response, "message_id", None) or response)
        _log.info("qstash.scheduled_at", endpoint=endpoint, deliver_at=deliver_at.isoformat(), message_id=msg_id)
        return msg_id
    except Exception as exc:
        report_error("qstash.schedule_at_failed", exc, endpoint=endpoint)
        return None


async def list_schedules() -> list[Any]:
    try:
        client = _get_client()
        return await client.schedule.list()
    except Exception as exc:
        report_error("qstash.list_schedules_failed", exc)
        return []


async def delete_schedule(schedule_id: str) -> None:
    try:
        client = _get_client()
        await client.schedule.delete(schedule_id)
        _log.info("qstash.schedule_deleted", schedule_id=schedule_id)
    except Exception as exc:
        report_error("qstash.delete_schedule_failed", exc, schedule_id=schedule_id)
