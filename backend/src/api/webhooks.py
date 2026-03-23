"""Webhook endpoints — email inbound.

The QStash synthesis webhook has been moved to the jobs router where it belongs
(all QStash-dispatched endpoints share the same router-level auth dependency).
"""

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.core.models import UserProfile
from src.core.settings import get_settings
from src.telemetry.logger import get_logger

router = APIRouter()
logger = get_logger("api.webhooks")


def _verify_email_webhook_signature(request: Request, body: bytes) -> None:
    """Verify the inbound email webhook using HMAC-SHA256.

    The sending service (SendGrid Inbound Parse, Postmark, etc.) must be
    configured with the same ``EMAIL_WEBHOOK_SECRET``.  The signature is
    expected in the ``X-Webhook-Signature`` header as a hex-encoded
    HMAC-SHA256 of the raw request body.
    """
    settings = get_settings()
    secret = settings.EMAIL_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=403, detail="Email webhook not configured")

    signature = request.headers.get("X-Webhook-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-Webhook-Signature header")

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        logger.warning("email.signature_invalid")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


@router.post("/webhooks/email/inbound")
async def email_forwarding_webhook(request: Request):
    """Webhook for email forwarding — parse and dispatch to cold path.

    Requires a valid HMAC-SHA256 signature in ``X-Webhook-Signature``.
    """
    body = await request.body()
    _verify_email_webhook_signature(request, body)

    form_data = await request.form()
    sender = form_data.get("from", "")
    text_body = form_data.get("text", "")
    to_address = form_data.get("to", "")

    if not text_body:
        return {"status": "empty"}

    logger.info("email.received", sender=str(sender)[:50])

    alias = str(to_address).split("@")[0] if to_address else ""
    if not alias:
        logger.warning("email.missing_to_address")
        return {"status": "missing_to"}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile.id).where(UserProfile.email_alias == alias)
        )
        user_id = result.scalar_one_or_none()

    if not user_id:
        logger.warning("email.unknown_alias", alias=alias)
        raise HTTPException(status_code=404, detail="Unknown email alias")

    from src.integrations.qstash import dispatch_job

    await dispatch_job("process-message", {
        "user_id": str(user_id),
        "message": str(text_body),
    })

    return {"status": "dispatched"}
