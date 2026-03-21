from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil import parser
from src.telemetry.logger import get_logger

_log = get_logger("db.utils")

def normalize_datetime(
    value: str | datetime | None, 
    user_tz_name: str | None = None
) -> datetime | None:
    """
    Parse a datetime string or object and return a UTC-normalized datetime.
    
    1. If the input is already a datetime, ensure it's timezone-aware.
    2. If it's a string, try ISO format first, then fall back to dateutil.parser.
    3. If naive, assume user_tz_name (or UTC if missing).
    4. Convert to UTC before returning.
    """
    if value is None:
        return None
    
    dt = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        if not value.strip():
            return None
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            try:
                dt = parser.parse(value)
            except (ValueError, TypeError, OverflowError):
                _log.warning("db.normalize_datetime_failed", value=value[:50])
                return None
    else:
        _log.warning("db.normalize_datetime_invalid_type", type=type(value).__name__)
        return None

    # Handle timezone
    if dt.tzinfo is None:
        # Naive datetime. Assume user's timezone or UTC.
        try:
            tz = ZoneInfo(user_tz_name) if user_tz_name else timezone.utc
        except Exception:
            tz = timezone.utc
        dt = dt.replace(tzinfo=tz)
    
    # Normalize to UTC
    return dt.astimezone(timezone.utc)
