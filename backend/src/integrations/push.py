import asyncio
import json

from pywebpush import WebPushException, webpush

from src.config import get_settings
from src.db.supabase import delete_push_subscription
from src.telemetry.logger import get_logger

_log = get_logger("integrations.push")


async def send_push_notification(
    subscription: dict,
    title: str,
    body: str,
    user_id: str | None = None,
) -> bool:
    settings = get_settings()

    payload = json.dumps({"title": title, "body": body})

    subscription_info = {
        "endpoint": subscription.get("endpoint", ""),
        "keys": {
            "p256dh": subscription.get("p256dh", ""),
            "auth": subscription.get("auth_key", ""),
        },
    }

    if not subscription_info["endpoint"]:
        _log.warning("push.missing_endpoint", user_id=user_id)
        return False

    try:
        # webpush is synchronous — run in thread pool to avoid blocking event loop
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:notifications@unspool.life"},
        )
        _log.info("push.sent", endpoint=subscription_info["endpoint"][:50])
        return True
    except WebPushException as exc:
        if exc.response and exc.response.status_code == 410:
            _log.info("push.subscription_expired", endpoint=subscription_info["endpoint"][:50])
            if user_id:
                try:
                    await delete_push_subscription(user_id, subscription_info["endpoint"])
                except Exception:
                    _log.warning("push.delete_subscription_failed", exc_info=True)
            return False
        _log.warning(
            "push.failed",
            endpoint=subscription_info["endpoint"][:50],
            error=str(exc),
        )
        return False
    except Exception:
        _log.warning("push.unexpected_error", exc_info=True)
        return False
