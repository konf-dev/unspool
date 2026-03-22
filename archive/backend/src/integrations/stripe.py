import asyncio

import stripe

from src.config import get_settings
from src.db.redis import cache_delete
from src.db.supabase import create_subscription, update_subscription
from src.telemetry.logger import get_logger

_log = get_logger("integrations.stripe")


async def create_checkout_session(user_id: str, email: str) -> str:
    settings = get_settings()
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        mode="subscription",
        customer_email=email,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 800,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": "Unspool Unlimited"},
                },
                "quantity": 1,
            }
        ],
        success_url=f"{settings.FRONTEND_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=settings.FRONTEND_URL,
        metadata={"user_id": user_id},
    )

    _log.info("stripe.checkout_created", user_id=user_id)
    return session.url or ""


async def handle_webhook(payload: bytes, signature: str) -> dict:
    settings = get_settings()
    stripe.api_key = settings.STRIPE_SECRET_KEY

    event = await asyncio.to_thread(
        stripe.Webhook.construct_event,
        payload,
        signature,
        settings.STRIPE_WEBHOOK_SECRET,
    )

    event_type = event["type"]
    _log.info("stripe.webhook_received", event_type=event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"]["user_id"]
        await create_subscription(
            user_id=user_id,
            tier="paid",
            stripe_customer_id=session.get("customer", ""),
            stripe_subscription_id=session.get("subscription", ""),
        )
        await cache_delete(f"session:{user_id}:tier")
        _log.info("stripe.subscription_created", user_id=user_id)

    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription["customer"]
        await _update_by_customer(customer_id, tier="free", status="cancelled")

    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        customer_id = invoice["customer"]
        await _update_by_customer(customer_id, status="past_due")

    return {"event_type": event_type}


async def _update_by_customer(customer_id: str, **fields: str) -> None:
    from src.db.supabase import get_subscription_by_customer

    sub = await get_subscription_by_customer(customer_id)
    if sub:
        await update_subscription(sub["user_id"], **fields)
        await cache_delete(f"session:{sub['user_id']}:tier")
        _log.info("stripe.subscription_updated", customer_id=customer_id, **fields)
