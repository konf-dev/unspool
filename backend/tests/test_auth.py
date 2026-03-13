import time

import pytest
from fastapi import HTTPException
from jose import jwt

from src.auth.supabase_auth import get_current_user, verify_jwt
from src.config import get_settings


def _make_token(sub: str = "user-123", exp_offset: int = 3600, secret: str | None = None) -> str:
    settings = get_settings()
    payload = {
        "sub": sub,
        "exp": int(time.time()) + exp_offset,
        "iss": "supabase",
    }
    return jwt.encode(payload, secret or settings.SUPABASE_JWT_SIGNING_SECRET, algorithm="HS256")


class TestVerifyJwt:
    def test_valid_token(self) -> None:
        token = _make_token(sub="abc-123")
        user_id = verify_jwt(token)
        assert user_id == "abc-123"

    def test_expired_token(self) -> None:
        token = _make_token(exp_offset=-10)
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401

    def test_wrong_secret(self) -> None:
        token = _make_token(secret="wrong-secret-that-is-long-enough")
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401

    def test_missing_sub(self) -> None:
        settings = get_settings()
        payload = {"exp": int(time.time()) + 3600, "iss": "supabase"}
        token = jwt.encode(payload, settings.SUPABASE_JWT_SIGNING_SECRET, algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401
        assert "sub" in exc_info.value.detail.lower()

    def test_garbage_token(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt("not.a.real.token")
        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_missing_header(self) -> None:
        class FakeRequest:
            headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(FakeRequest())  # type: ignore[arg-type]
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_bearer_prefix(self) -> None:
        class FakeRequest:
            headers = {"Authorization": "Basic abc123"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(FakeRequest())  # type: ignore[arg-type]
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_bearer(self) -> None:
        token = _make_token(sub="user-456")

        class FakeRequest:
            headers = {"Authorization": f"Bearer {token}"}

        user_id = await get_current_user(FakeRequest())  # type: ignore[arg-type]
        assert user_id == "user-456"
