from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.auth.supabase_auth import get_current_user
from src.db.supabase import save_push_subscription
from src.integrations.stripe import create_checkout_session, handle_webhook
from src.telemetry.logger import get_logger

_log = get_logger("api.subscribe")

router = APIRouter()


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


@router.post("/subscribe")
async def subscribe(user_id: str = Depends(get_current_user)) -> dict:
    # Stripe checkout needs an email. Try to get it from the profile display_name
    # or fall back to user_id (Supabase Auth stores email in auth.users, not user_profiles).
    from src.db.supabase import get_profile

    email = ""
    try:
        profile = await get_profile(user_id)
        email = profile.get("display_name", "") if profile else ""
    except Exception:
        pass

    try:
        url = await create_checkout_session(user_id, email=email or user_id)
    except Exception:
        _log.error("subscribe.checkout_failed", user_id=user_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not create checkout session")
    return {"url": url}


@router.post("/push/subscribe")
async def push_subscribe(
    request: PushSubscriptionRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    await save_push_subscription(
        user_id=user_id,
        endpoint=request.endpoint,
        p256dh=request.keys.p256dh,
        auth_key=request.keys.auth,
    )
    return {"status": "subscribed"}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        result = await handle_webhook(payload, signature)
    except Exception as exc:
        _log.warning("stripe.webhook_error", error=str(exc))
        raise HTTPException(
            status_code=400, detail="Webhook verification failed"
        ) from exc

    return result
