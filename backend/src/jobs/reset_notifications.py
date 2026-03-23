"""Reset notification_sent_today flag for all users."""

from sqlalchemy import update

from src.core.database import AsyncSessionLocal
from src.core.models import UserProfile
from src.telemetry.logger import get_logger

_log = get_logger("jobs.reset_notifications")


async def run_reset_notifications() -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(UserProfile).where(
                UserProfile.notification_sent_today.is_(True)
            ).values(notification_sent_today=False)
        )
        count = result.rowcount
        await session.commit()

    _log.info("reset_notifications.done", reset_count=count)
    return {"reset": count}
