"""Tests for smart_fetch tool — timeframe parsing, entity resolution, query construction, security."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.query_tools import _parse_timeframe, smart_fetch


class TestParseTimeframe:
    def test_last_week(self) -> None:
        result = _parse_timeframe("last_week")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2

    def test_last_month(self) -> None:
        result = _parse_timeframe("last_month")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_last_3_months(self) -> None:
        result = _parse_timeframe("last_3_months")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=90)
        assert abs((result - expected).total_seconds()) < 2

    def test_last_year(self) -> None:
        result = _parse_timeframe("last_year")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=365)
        assert abs((result - expected).total_seconds()) < 2

    def test_last_n_days(self) -> None:
        result = _parse_timeframe("last_14_days")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=14)
        assert abs((result - expected).total_seconds()) < 2

    def test_last_1_day(self) -> None:
        result = _parse_timeframe("last_1_day")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_none_returns_none(self) -> None:
        assert _parse_timeframe(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_timeframe("") is None

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_timeframe("yesterday") is None
        assert _parse_timeframe("2026-01-01") is None
        assert _parse_timeframe("random_text") is None

    def test_large_n_days(self) -> None:
        """Edge case: very large lookback — should not crash."""
        result = _parse_timeframe("last_3650_days")
        assert result is not None
        expected = datetime.now(timezone.utc) - timedelta(days=3650)
        assert abs((result - expected).total_seconds()) < 2


class TestSmartFetch:
    @pytest.mark.asyncio
    async def test_items_only(self) -> None:
        mock_items = [{"id": "i1", "interpreted_action": "buy groceries"}]

        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=mock_items)

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items"], "status_filter": "open", "limit": 5},
            )

        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "i1"
        mock_db.get_items_filtered.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_sources(self) -> None:
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[{"id": "i1"}])
            mock_db.get_memories_filtered = AsyncMock(return_value=[{"id": "m1"}])
            mock_db.get_messages_filtered = AsyncMock(return_value=[{"id": "msg1"}])

            result = await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["items", "memories", "messages"],
                    "text_query": "thesis",
                    "limit": 10,
                },
            )

        assert "items" in result
        assert "memories" in result
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_entity_resolution(self) -> None:
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value="entity-uuid-123")
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["items"],
                    "entity": "Erik",
                    "limit": 5,
                },
            )

        mock_db.resolve_entity.assert_called_once_with("u1", "Erik")
        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["entity_id"] == "entity-uuid-123"

    @pytest.mark.asyncio
    async def test_entity_not_found(self) -> None:
        """When entity doesn't exist, should still search without entity filter."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items"], "entity": "NonexistentPerson"},
            )

        assert "items" in result
        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["entity_id"] is None

    @pytest.mark.asyncio
    async def test_timeframe_passed_to_queries(self) -> None:
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["items"],
                    "timeframe": "last_week",
                    "limit": 5,
                },
            )

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["since"] is not None
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs((call_kwargs["since"] - expected).total_seconds()) < 2

    @pytest.mark.asyncio
    async def test_calendar_source(self) -> None:
        mock_events = [
            {"summary": "Meeting with Chen", "start_at": "2026-03-20T14:00:00Z"}
        ]

        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_calendar_events_filtered = AsyncMock(return_value=mock_events)

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["calendar"], "limit": 20},
            )

        assert "calendar" in result
        assert len(result["calendar"]) == 1

    @pytest.mark.asyncio
    async def test_source_failure_returns_empty_list(self) -> None:
        """If one source fails, others should still work."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(
                side_effect=ConnectionError("DB down")
            )
            mock_db.get_memories_filtered = AsyncMock(return_value=[{"id": "m1"}])

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items", "memories"], "limit": 10},
            )

        assert result["items"] == []
        assert len(result["memories"]) == 1

    @pytest.mark.asyncio
    async def test_unknown_source_ignored(self) -> None:
        """Unknown source names should not crash."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items", "emails"], "limit": 5},
            )

        assert "items" in result
        assert "emails" not in result

    @pytest.mark.asyncio
    async def test_default_sources(self) -> None:
        """Missing sources key defaults to ['items']."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(user_id="u1", query_spec={})

        assert "items" in result
        mock_db.get_items_filtered.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_limit(self) -> None:
        """Missing limit defaults to 10."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(user_id="u1", query_spec={"sources": ["items"]})

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_status_filter_all_passes_none(self) -> None:
        """status_filter='all' should pass None to DB (no filter)."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items"], "status_filter": "all"},
            )

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["status"] is None

    @pytest.mark.asyncio
    async def test_messages_use_entity_name_as_search(self) -> None:
        """When searching messages with an entity, entity name should be used as text search."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value="e-uuid")
            mock_db.get_messages_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["messages"],
                    "entity": "Erik",
                    "limit": 5,
                },
            )

        call_kwargs = mock_db.get_messages_filtered.call_args[1]
        assert call_kwargs["search_text"] == "Erik"


class TestSmartFetchSecurity:
    """Security-focused tests for smart_fetch."""

    @pytest.mark.asyncio
    async def test_entity_with_sql_injection_attempt(self) -> None:
        """Entity name with SQL injection should be passed as parameterized value, not raw SQL."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["items"],
                    "entity": "'; DROP TABLE items; --",
                },
            )

        # Entity goes through resolve_entity as a parameterized query
        mock_db.resolve_entity.assert_called_once_with("u1", "'; DROP TABLE items; --")

    @pytest.mark.asyncio
    async def test_text_query_with_sql_injection_attempt(self) -> None:
        """text_query with SQL should be safe — passed as parameterized value."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_memories_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={
                    "sources": ["memories"],
                    "text_query": "x' OR '1'='1",
                },
            )

        call_kwargs = mock_db.get_memories_filtered.call_args[1]
        assert call_kwargs["search_text"] == "x' OR '1'='1"

    @pytest.mark.asyncio
    async def test_user_id_isolation(self) -> None:
        """Each call should only query for the specified user_id."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="user-abc",
                query_spec={"sources": ["items"]},
            )

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["user_id"] == "user-abc"

    @pytest.mark.asyncio
    async def test_excessive_limit_capped(self) -> None:
        """Large limit values are capped at 100 to prevent DB overload."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items"], "limit": 10000},
            )

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["limit"] == 100


class TestSmartFetchEdgeCases:
    """Edge cases for long-term usage."""

    @pytest.mark.asyncio
    async def test_string_query_spec_fallback(self) -> None:
        """If LLM JSON parse fails, smart_fetch receives a string — should fallback gracefully."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(
                user_id="u1",
                query_spec="this is not valid json that the LLM returned",
            )

        assert isinstance(result, dict)
        assert "items" in result
        mock_db.get_items_filtered.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_query_spec_fallback(self) -> None:
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(user_id="u1", query_spec=None)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self) -> None:
        """Excessive limits should be capped to prevent DB overload."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items"], "limit": 50000},
            )

        call_kwargs = mock_db.get_items_filtered.call_args[1]
        assert call_kwargs["limit"] == 100

    @pytest.mark.asyncio
    async def test_empty_query_spec(self) -> None:
        """Completely empty query_spec should use defaults and not crash."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(return_value=[])

            result = await smart_fetch(user_id="u1", query_spec={})

        assert isinstance(result, dict)
        assert "items" in result

    @pytest.mark.asyncio
    async def test_empty_sources_list(self) -> None:
        """Empty sources list should return empty results."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": []},
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_all_sources_fail(self) -> None:
        """If every source fails, should return empty lists for each."""
        with patch("src.tools.query_tools.db") as mock_db:
            mock_db.resolve_entity = AsyncMock(return_value=None)
            mock_db.get_items_filtered = AsyncMock(side_effect=Exception("fail"))
            mock_db.get_memories_filtered = AsyncMock(side_effect=Exception("fail"))
            mock_db.get_messages_filtered = AsyncMock(side_effect=Exception("fail"))

            result = await smart_fetch(
                user_id="u1",
                query_spec={"sources": ["items", "memories", "messages"]},
            )

        assert result["items"] == []
        assert result["memories"] == []
        assert result["messages"] == []
