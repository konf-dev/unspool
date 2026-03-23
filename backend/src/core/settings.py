"""Centralized settings via pydantic-settings. Replaces core/config.py."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Supabase ---
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWT_SIGNING_SECRET: str = ""

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    ECHO_SQL: bool = False

    # --- Redis ---
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""

    # --- QStash ---
    QSTASH_TOKEN: str = ""
    QSTASH_URL: str = ""
    QSTASH_CURRENT_SIGNING_KEY: str = ""
    QSTASH_NEXT_SIGNING_KEY: str = ""

    # --- LLM ---
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4.1"
    LLM_MODEL_FAST: str = "gpt-4.1-mini"

    # --- Embeddings ---
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- Legacy OpenAI key (used by existing code) ---
    OPENAI_API_KEY: str = ""

    # --- URLs ---
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    API_URL: str = "http://localhost:8000"

    # --- Push Notifications ---
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""

    # --- Stripe ---
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # --- Auth ---
    ADMIN_API_KEY: str = ""
    EVAL_API_KEY: str = ""

    # --- Observability ---
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

    # --- Email Webhook ---
    EMAIL_WEBHOOK_SECRET: str = ""

    # --- CORS ---
    CORS_EXTRA_ORIGINS: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.ENVIRONMENT != "development":
        missing = [
            name
            for name in (
                "SUPABASE_URL",
                "SUPABASE_SERVICE_KEY",
                "DATABASE_URL",
            )
            if not getattr(s, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required config in {s.ENVIRONMENT}: {', '.join(missing)}"
            )
    # Backfill: if LLM_API_KEY not set, fall back to OPENAI_API_KEY
    if not s.LLM_API_KEY and s.OPENAI_API_KEY:
        object.__setattr__(s, "LLM_API_KEY", s.OPENAI_API_KEY)
    if not s.EMBEDDING_API_KEY and (s.LLM_API_KEY or s.OPENAI_API_KEY):
        object.__setattr__(s, "EMBEDDING_API_KEY", s.LLM_API_KEY or s.OPENAI_API_KEY)
    return s
