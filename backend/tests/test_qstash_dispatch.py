"""Tests for QStash client wrapper — dispatch, scheduling, URL construction, error handling."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.qstash import (
    _build_url,
    dispatch_at,
    dispatch_job,
    schedule_cron,
)


class TestBuildUrl:
    def test_basic_url(self) -> None:
        with patch("src.integrations.qstash.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(API_URL="https://api.unspool.life")
            url = _build_url("process-conversation")
            assert url == "https://api.unspool.life/jobs/process-conversation"

    def test_trailing_slash_stripped(self) -> None:
        with patch("src.integrations.qstash.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(API_URL="https://api.unspool.life/")
            url = _build_url("check-deadlines")
            assert url == "https://api.unspool.life/jobs/check-deadlines"

    def test_no_double_slashes(self) -> None:
        with patch("src.integrations.qstash.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(API_URL="https://api.unspool.life")
            url = _build_url("decay-urgency")
            assert "//" not in url.replace("https://", "")


class TestDispatchJob:
    @pytest.fixture(autouse=True)
    def _reset_client(self) -> None:
        import src.integrations.qstash as mod

        mod._client = None

    @pytest.mark.asyncio
    async def test_dispatch_with_delay_string(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock(message_id="msg-123")
        mock_client.message.publish_json = AsyncMock(return_value=mock_response)

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await dispatch_job(
                "process-conversation",
                {"user_id": "u1", "message_ids": ["m1"]},
                delay="10s",
            )

        assert result == "msg-123"
        mock_client.message.publish_json.assert_called_once()
        call_kwargs = mock_client.message.publish_json.call_args[1]
        assert call_kwargs["delay"] == "10s"
        assert call_kwargs["body"]["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_dispatch_with_int_delay(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(
            return_value=MagicMock(message_id="msg-456")
        )

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await dispatch_job("check-deadlines", {}, delay=30)

        assert result == "msg-456"
        call_kwargs = mock_client.message.publish_json.call_args[1]
        assert call_kwargs["delay"] == 30

    @pytest.mark.asyncio
    async def test_dispatch_zero_delay_sends_none(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(
            return_value=MagicMock(message_id="msg-789")
        )

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            await dispatch_job("decay-urgency", {}, delay=0)

        call_kwargs = mock_client.message.publish_json.call_args[1]
        assert call_kwargs["delay"] is None

    @pytest.mark.asyncio
    async def test_dispatch_failure_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(
            side_effect=ConnectionError("timeout")
        )

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await dispatch_job("process-conversation", {"user_id": "u1"})

        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_includes_correct_url(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(
            return_value=MagicMock(message_id="msg-x")
        )

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.unspool.life")
            await dispatch_job("sync-calendar", {})

        call_kwargs = mock_client.message.publish_json.call_args[1]
        assert call_kwargs["url"] == "https://api.unspool.life/jobs/sync-calendar"


class TestScheduleCron:
    @pytest.fixture(autouse=True)
    def _reset_client(self) -> None:
        import src.integrations.qstash as mod

        mod._client = None

    @pytest.mark.asyncio
    async def test_schedule_with_id(self) -> None:
        mock_client = MagicMock()
        mock_client.schedule.create = AsyncMock(return_value="sched-123")

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await schedule_cron(
                "check-deadlines", "0 * * * *", schedule_id="unspool-check-deadlines"
            )

        assert result == "sched-123"
        call_kwargs = mock_client.schedule.create.call_args[1]
        assert call_kwargs["cron"] == "0 * * * *"
        assert call_kwargs["schedule_id"] == "unspool-check-deadlines"

    @pytest.mark.asyncio
    async def test_schedule_failure_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_client.schedule.create = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await schedule_cron("bad-job", "* * * * *")

        assert result is None


class TestDispatchAt:
    @pytest.fixture(autouse=True)
    def _reset_client(self) -> None:
        import src.integrations.qstash as mod

        mod._client = None

    @pytest.mark.asyncio
    async def test_dispatch_at_converts_to_unix(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(
            return_value=MagicMock(message_id="msg-at-1")
        )
        target_time = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await dispatch_at(
                "nudge-item", {"item_id": "i1"}, deliver_at=target_time
            )

        assert result == "msg-at-1"
        call_kwargs = mock_client.message.publish_json.call_args[1]
        assert call_kwargs["not_before"] == int(target_time.timestamp())
        assert "delay" not in call_kwargs or call_kwargs.get("delay") is None

    @pytest.mark.asyncio
    async def test_dispatch_at_rejects_naive_datetime(self) -> None:
        naive_time = datetime(2026, 3, 20, 14, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            await dispatch_at("nudge-item", {}, deliver_at=naive_time)

    @pytest.mark.asyncio
    async def test_dispatch_at_failure_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_client.message.publish_json = AsyncMock(side_effect=RuntimeError("fail"))
        target_time = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)

        with (
            patch("src.integrations.qstash._get_client", return_value=mock_client),
            patch("src.integrations.qstash.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(API_URL="https://api.test.com")
            result = await dispatch_at("nudge-item", {}, deliver_at=target_time)

        assert result is None
