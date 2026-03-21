import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from src.db.utils import normalize_datetime

def test_normalize_datetime_iso():
    # Valid ISO string
    res = normalize_datetime("2026-03-20T14:30:00Z")
    assert res == datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc)

def test_normalize_datetime_flexible_string():
    # Flexible string via dateutil
    res = normalize_datetime("March 20, 2026 2:30 PM", "UTC")
    assert res == datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc)

def test_normalize_datetime_naive_with_tz():
    # Naive string + user timezone
    # Assume user is in EST (-5)
    res = normalize_datetime("2026-03-20 14:30:00", "America/New_York")
    # 14:30 EST is 19:30 UTC
    assert res == datetime(2026, 3, 20, 18, 30, tzinfo=timezone.utc) # Wait, New York is -4 in March (DST)?
    # Actually March 20 2026 is after DST starts (March 8 2026)
    # So it should be -4. 14:30 - (-4) = 18:30 UTC. Correct.

def test_normalize_datetime_none():
    assert normalize_datetime(None) is None

def test_normalize_datetime_invalid():
    assert normalize_datetime("not a date") is None

def test_normalize_datetime_object():
    dt = datetime(2026, 3, 20, 14, 30, tzinfo=timezone.utc)
    assert normalize_datetime(dt) == dt
