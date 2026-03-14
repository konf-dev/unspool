import time
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException

from src.auth.supabase_auth import get_current_user, verify_jwt
from src.config import get_settings


# Generate a test ES256 key pair
_private_key = ec.generate_private_key(ec.SECP256R1())
_public_key = _private_key.public_key()
_public_key_pem = _public_key.public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)
_kid = "test-key-id"


def _make_token(
    sub: str = "user-123",
    exp_offset: int = 3600,
    aud: str = "authenticated",
    iss: str | None = None,
) -> str:
    settings = get_settings()
    payload = {
        "sub": sub,
        "exp": int(time.time()) + exp_offset,
        "aud": aud,
        "iss": iss or f"{settings.SUPABASE_URL}/auth/v1",
    }
    return pyjwt.encode(
        payload,
        _private_key,
        algorithm="ES256",
        headers={"kid": _kid},
    )


def _mock_jwk_client():
    """Create a mock PyJWKClient that returns our test public key."""
    mock_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = _public_key
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
    return mock_client


class TestVerifyJwt:
    def test_valid_token(self) -> None:
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            token = _make_token(sub="abc-123")
            user_id = verify_jwt(token)
            assert user_id == "abc-123"

    def test_expired_token(self) -> None:
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            token = _make_token(exp_offset=-10)
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401

    def test_wrong_key(self) -> None:
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        token = pyjwt.encode(
            {
                "sub": "user-123",
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                "iss": f"{get_settings().SUPABASE_URL}/auth/v1",
            },
            wrong_key,
            algorithm="ES256",
            headers={"kid": _kid},
        )
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401

    def test_missing_sub(self) -> None:
        settings = get_settings()
        token = pyjwt.encode(
            {
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                "iss": f"{settings.SUPABASE_URL}/auth/v1",
            },
            _private_key,
            algorithm="ES256",
            headers={"kid": _kid},
        )
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401

    def test_wrong_audience(self) -> None:
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            token = _make_token(aud="wrong-audience")
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401

    def test_wrong_issuer(self) -> None:
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            token = _make_token(iss="https://evil.supabase.co/auth/v1")
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401

    def test_garbage_token(self) -> None:
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            mock_client = _mock_jwk_client()
            mock_client.get_signing_key_from_jwt.side_effect = pyjwt.InvalidTokenError(
                "bad"
            )
            with patch(
                "src.auth.supabase_auth._get_jwk_client", return_value=mock_client
            ):
                with pytest.raises(HTTPException) as exc_info:
                    verify_jwt("not.a.real.token")
                assert exc_info.value.status_code == 401

    def test_hs256_algorithm_rejected(self) -> None:
        """Ensure HS256 tokens are rejected (algorithm confusion attack prevention)."""
        settings = get_settings()
        token = pyjwt.encode(
            {
                "sub": "attacker",
                "exp": int(time.time()) + 3600,
                "aud": "authenticated",
                "iss": f"{settings.SUPABASE_URL}/auth/v1",
            },
            "some-secret",
            algorithm="HS256",
        )
        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
            assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_missing_header(self) -> None:
        class FakeRequest:
            headers: dict[str, str] = {}

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

        with patch(
            "src.auth.supabase_auth._get_jwk_client", return_value=_mock_jwk_client()
        ):
            user_id = await get_current_user(FakeRequest())  # type: ignore[arg-type]
            assert user_id == "user-456"
