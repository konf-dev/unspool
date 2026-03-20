from datetime import datetime
from typing import Any

from qstash import AsyncQStash

from src.config import get_settings
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

_log = get_logger("integrations.qstash")

_client: AsyncQStash | None = None


def _get_client() -> AsyncQStash:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQStash(token=settings.QSTASH_TOKEN)
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
    """Dispatch a delayed job to /jobs/{endpoint}.

    delay accepts: int (seconds), or string ("10s", "5m", "1h").
    QStash SDK handles the string format natively.

    Returns the QStash message ID, or None on failure.
    """
    url = _build_url(endpoint)
    try:
        client = _get_client()
        response = await client.message.publish_json(
            url=url,
            body=payload,
            delay=delay if delay else None,
        )
        msg_id = str(getattr(response, "message_id", None) or response)
        _log.info(
            "qstash.dispatched",
            endpoint=endpoint,
            delay=delay,
            message_id=msg_id,
        )
        return msg_id
    except Exception as exc:
        report_error("qstash.dispatch_failed", exc, endpoint=endpoint)
        return None


async def schedule_cron(
    endpoint: str,
    cron_expression: str,
    schedule_id: str | None = None,
) -> str | None:
    """Create or update a QStash cron schedule. Idempotent via schedule_id.

    Returns the schedule ID, or None on failure.
    """
    url = _build_url(endpoint)
    try:
        client = _get_client()
        sid = await client.schedule.create(
            destination=url,
            cron=cron_expression,
            schedule_id=schedule_id,
        )
        _log.info(
            "qstash.cron_registered",
            endpoint=endpoint,
            cron=cron_expression,
            schedule_id=sid,
        )
        return sid
    except Exception as exc:
        report_error("qstash.cron_registration_failed", exc, endpoint=endpoint)
        return None


async def dispatch_at(
    endpoint: str,
    payload: dict[str, Any],
    deliver_at: datetime,
) -> str | None:
    """Dispatch a one-shot job at a specific future datetime.

    Used for scheduled reminders/nudges. deliver_at must be timezone-aware.

    Returns the QStash message ID, or None on failure.
    """
    if deliver_at.tzinfo is None:
        raise ValueError("deliver_at must be timezone-aware")
    url = _build_url(endpoint)
    not_before = int(deliver_at.timestamp())
    try:
        client = _get_client()
        response = await client.message.publish_json(
            url=url,
            body=payload,
            not_before=not_before,
        )
        msg_id = str(getattr(response, "message_id", None) or response)
        _log.info(
            "qstash.scheduled_at",
            endpoint=endpoint,
            deliver_at=deliver_at.isoformat(),
            message_id=msg_id,
        )
        return msg_id
    except Exception as exc:
        report_error("qstash.schedule_at_failed", exc, endpoint=endpoint)
        return None
