"""ICS calendar feed from graph deadlines."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from icalendar import Calendar, Event
from sqlalchemy import text

from src.core.database import AsyncSessionLocal
from src.core.models import UserProfile
from src.telemetry.logger import get_logger
from sqlalchemy import select

_log = get_logger("api.feed")

router = APIRouter()


@router.get("/feed/{token}.ics")
async def ics_feed(token: str) -> Response:
    """ICS calendar feed — authenticated via token-in-URL (no auth header)."""
    async with AsyncSessionLocal() as session:
        # Look up user by feed token
        result = await session.execute(
            select(UserProfile).where(UserProfile.feed_token == token)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise HTTPException(status_code=404, detail="Feed not found")

        user_id = str(profile.id)

        # Query timeline view for deadlines
        rows = await session.execute(text("""
            SELECT node_id, content, deadline, deadline_type, created_at
            FROM vw_timeline
            WHERE user_id = :uid              AND deadline::timestamptz >= NOW() - interval '30 days'
            ORDER BY deadline::timestamptz
            LIMIT 100
        """), {"uid": user_id})

        items = rows.mappings().all()

    cal = Calendar()
    cal.add("prodid", "-//Unspool//unspool.life//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Unspool Deadlines")

    for item in items:
        try:
            deadline = item["deadline"]
            if not deadline:
                continue

            dt = datetime.fromisoformat(deadline) if isinstance(deadline, str) else deadline

            event = Event()
            event.add("summary", item["content"])
            event.add("dtstart", dt.date() if hasattr(dt, "date") else dt)
            event.add("uid", f"{item['node_id']}@unspool.life")

            if item.get("deadline_type") == "hard":
                event.add("description", "Hard deadline")

            cal.add_component(event)
        except Exception:
            continue

    return Response(
        content=cal.to_ical(),
        media_type="text/calendar",
        headers={"Content-Disposition": "inline; filename=unspool.ics"},
    )
