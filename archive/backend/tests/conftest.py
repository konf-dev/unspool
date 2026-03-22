import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-publishable-key")
os.environ.setdefault("SUPABASE_SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "SUPABASE_JWT_SIGNING_SECRET", "test-jwt-secret-at-least-32-chars-long"
)
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://test.upstash.io")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test-redis-token")
os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_MODEL_FAST", "test-model-fast")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("EMBEDDING_API_KEY", "test-embedding-key")
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ.setdefault("LANGFUSE_HOST", "")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "")

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from src.config import get_settings

    get_settings.cache_clear()
