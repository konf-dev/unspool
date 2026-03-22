from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
import logging
import uuid
from typing import Optional

from src.agents.cold_path.synthesis import run_nightly_synthesis
from src.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Very basic QStash signature verification placeholder
def verify_qstash_signature(request: Request):
    # In production, use qstash SDK's Receiver to verify Upstash-Signature header
    return True

class SynthesisPayload(BaseModel):
    user_id: str

@router.post("/webhooks/qstash/synthesis")
async def qstash_synthesis_webhook(payload: SynthesisPayload, request: Request):
    """Triggered by a QStash cron schedule at 3 AM."""
    verify_qstash_signature(request)
    
    try:
        user_uuid = uuid.UUID(payload.user_id)
        await run_nightly_synthesis(user_uuid)
        return {"status": "success", "message": "Synthesis complete"}
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="Synthesis failed")

@router.post("/webhooks/email/inbound")
async def email_forwarding_webhook(request: Request):
    """
    Webhook for SendGrid/Postmark inbound parse.
    Extracts the body of a forwarded email and dumps it into the Event Stream via the Cold Path.
    """
    # For this MVP, we just acknowledge receipt
    # In production, parse the multi-part form data, extract 'text', and map 'to' address to a user_id
    form_data = await request.form()
    sender = form_data.get("from")
    text_body = form_data.get("text")
    
    logger.info(f"Received email from {sender}")
    # TODO: await process_brain_dump(user_id, text_body)
    
    return {"status": "received"}
