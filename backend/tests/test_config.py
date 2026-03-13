import os

import pytest

from src.config import get_settings


class TestSettings:
    def test_defaults_in_development(self) -> None:
        settings = get_settings()
        assert settings.ENVIRONMENT == "development"
        assert settings.SUPABASE_URL == "https://test.supabase.co"

    def test_fail_fast_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SUPABASE_URL", "")
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
        monkeypatch.setenv("SUPABASE_JWT_SIGNING_SECRET", "")
        monkeypatch.setenv("DATABASE_URL", "")

        with pytest.raises(RuntimeError, match="Missing required config"):
            get_settings()

    def test_production_with_all_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SUPABASE_URL", "https://prod.supabase.co")
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret")
        monkeypatch.setenv("SUPABASE_JWT_SIGNING_SECRET", "jwt-secret")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")

        settings = get_settings()
        assert settings.ENVIRONMENT == "production"
