from datetime import datetime, timedelta, timezone

import httpx

from src.config import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("integrations.google_calendar")

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


async def refresh_access_token(refresh_token: str) -> str | None:
    settings = get_settings()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            },
        )

    if resp.status_code != 200:
        _log.warning("google.token_refresh_failed", status=resp.status_code)
        return None

    data = resp.json()
    return data.get("access_token")


async def fetch_calendar_events(
    access_token: str,
    days_ahead: int = 7,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    events: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_CALENDAR_API}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": "100",
            },
        )

    if resp.status_code != 200:
        _log.warning("google.calendar_fetch_failed", status=resp.status_code)
        return events

    data = resp.json()
    for item in data.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})
        events.append(
            {
                "google_event_id": item["id"],
                "summary": item.get("summary", ""),
                "start_at": start.get("dateTime", start.get("date", "")),
                "end_at": end.get("dateTime", end.get("date", "")),
                "location": item.get("location"),
                "description": item.get("description"),
                "is_all_day": "date" in start,
            }
        )

    _log.info("google.calendar_fetched", event_count=len(events))
    return events
