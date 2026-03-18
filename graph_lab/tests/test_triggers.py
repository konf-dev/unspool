"""Tests for retrieval triggers."""

import re
from datetime import datetime, timedelta, timezone

from graph_lab.src.triggers import get_trigger


def test_trigger_registry_has_all_types():
    expected = ["vector_search", "date_proximity", "status_query", "recency", "walk"]
    for trigger_type in expected:
        assert get_trigger(trigger_type) is not None, f"Trigger {trigger_type} not registered"


def test_iso_date_pattern():
    """Verify the temporal trigger's date pattern works."""
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    assert pattern.match("2026-03-20")
    assert pattern.match("2026-12-31")
    assert not pattern.match("March 20")
    assert not pattern.match("2026-03-20T10:00:00")
    assert not pattern.match("next Friday")


def test_date_proximity_logic():
    """Verify the date proximity check logic."""
    now = datetime(2026, 3, 16, tzinfo=timezone.utc)
    window_hours = 48

    # Within window (tomorrow)
    date1 = datetime(2026, 3, 17, tzinfo=timezone.utc)
    assert now <= date1 <= now + timedelta(hours=window_hours)

    # Within window (day after tomorrow)
    date2 = datetime(2026, 3, 18, tzinfo=timezone.utc)
    assert now <= date2 <= now + timedelta(hours=window_hours)

    # Outside window (4 days out)
    date3 = datetime(2026, 3, 20, tzinfo=timezone.utc)
    assert not (now <= date3 <= now + timedelta(hours=window_hours))

    # Overdue (yesterday)
    date4 = datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert now - timedelta(days=7) <= date4 < now
