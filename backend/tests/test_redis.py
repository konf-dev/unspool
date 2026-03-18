from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.redis import _decode_result, rate_limit_check


class TestDecodeResult:
    def test_none(self) -> None:
        assert _decode_result(None) is None

    def test_bytes(self) -> None:
        assert _decode_result(b"hello") == "hello"

    def test_string(self) -> None:
        assert _decode_result("world") == "world"

    def test_int(self) -> None:
        assert _decode_result(42) == "42"


class TestRateLimitCheck:
    @pytest.mark.asyncio
    async def test_first_request_allowed(self) -> None:
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock(return_value=mock_pipe)
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.exec = AsyncMock(return_value=[True, 1])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is True
            assert remaining == 9

    @pytest.mark.asyncio
    async def test_at_limit_still_allowed(self) -> None:
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock(return_value=mock_pipe)
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.exec = AsyncMock(return_value=[None, 10])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is True
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_denied(self) -> None:
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock(return_value=mock_pipe)
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.exec = AsyncMock(return_value=[None, 11])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_pipeline_calls_set_nx_then_incr(self) -> None:
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock(return_value=mock_pipe)
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.exec = AsyncMock(return_value=[True, 1])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            await rate_limit_check("user-1", 10)
            # Verify SET NX with ex=86400
            mock_pipe.set.assert_called_once()
            call_args = mock_pipe.set.call_args
            assert (
                call_args.kwargs.get("ex") == 86400 or call_args[1].get("ex") == 86400
            )
            assert call_args.kwargs.get("nx") is True or call_args[1].get("nx") is True
            # Verify INCR
            mock_pipe.incr.assert_called_once()
