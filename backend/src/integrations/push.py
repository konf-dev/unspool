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
        "endpoint": subscription["endpoint"],
        "keys": {
            "p256dh": subscription["p256dh"],
            "auth": subscription["auth_key"],
        },
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:notifications@unspool.life"},
        )
        _log.info("push.sent", endpoint=subscription["endpoint"][:50])
        return True
    except WebPushException as exc:
        if exc.response and exc.response.status_code == 410:
            _log.info("push.subscription_expired", endpoint=subscription["endpoint"][:50])
            if user_id:
                await delete_push_subscription(user_id, subscription["endpoint"])
            return False
        _log.warning(
            "push.failed",
            endpoint=subscription["endpoint"][:50],
            error=str(exc),
        )
        return False
