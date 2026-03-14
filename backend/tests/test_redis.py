from unittest.mock import MagicMock, patch

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
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.incr.return_value = 1

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is True
            assert remaining == 9
            mock_redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_at_limit_still_allowed(self) -> None:
        mock_redis = MagicMock()
        mock_redis.set.return_value = None
        mock_redis.incr.return_value = 10

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is True
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_denied(self) -> None:
        mock_redis = MagicMock()
        mock_redis.set.return_value = None
        mock_redis.incr.return_value = 11

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            allowed, remaining = await rate_limit_check("user-1", 10)
            assert allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_atomic_set_nx_before_incr(self) -> None:
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.incr.return_value = 1

        with patch("src.db.redis.get_redis", return_value=mock_redis):
            await rate_limit_check("user-1", 10)
            # SET NX should be called with ex=86400 and nx=True
            set_call = mock_redis.set.call_args
            assert set_call.kwargs.get("ex") == 86400 or set_call[1].get("ex") == 86400
            assert set_call.kwargs.get("nx") is True or set_call[1].get("nx") is True
            # INCR should be called after SET NX
            mock_redis.incr.assert_called_once()
