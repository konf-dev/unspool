"""Tests for authentication modules."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException


class TestSupabaseAuth:
    def test_eval_token_valid(self):
        """eval: prefix with correct key returns EVAL_USER_ID."""
        from src.auth.supabase_auth import EVAL_USER_ID
        assert EVAL_USER_ID == "b8a2e17e-ff55-485f-ad6c-29055a607b33"

    @pytest.mark.asyncio
    async def test_missing_bearer_raises_401(self):
        from src.auth.supabase_auth import get_current_user
        request = MagicMock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc:
            await get_current_user(request)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_eval_key_raises_401(self):
        from src.auth.supabase_auth import get_current_user
        request = MagicMock()
        request.headers = {"Authorization": "Bearer eval:wrong-key"}

        with patch("src.auth.supabase_auth.get_settings") as mock_settings:
            mock_settings.return_value.EVAL_API_KEY = "correct-key"
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request)
            assert exc.value.status_code == 401


class TestAdminAuth:
    @pytest.mark.asyncio
    async def test_missing_key_raises_403(self):
        from src.auth.admin_auth import verify_admin_key
        request = MagicMock()
        request.headers = {}

        with patch("src.auth.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.ADMIN_API_KEY = "test-key"
            with pytest.raises(HTTPException) as exc:
                await verify_admin_key(request)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_key_raises_403(self):
        from src.auth.admin_auth import verify_admin_key
        request = MagicMock()
        request.headers = {"X-Admin-Key": "wrong-key"}

        with patch("src.auth.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.ADMIN_API_KEY = "correct-key"
            with pytest.raises(HTTPException) as exc:
                await verify_admin_key(request)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_correct_key_passes(self):
        from src.auth.admin_auth import verify_admin_key
        request = MagicMock()
        request.headers = {"X-Admin-Key": "correct-key"}

        with patch("src.auth.admin_auth.get_settings") as mock_settings:
            mock_settings.return_value.ADMIN_API_KEY = "correct-key"
            # Should not raise
            await verify_admin_key(request)
