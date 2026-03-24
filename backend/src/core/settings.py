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

    # --- Provider API Keys (one per provider, shared across pipelines) ---
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # --- Chat (hot path) ---
    CHAT_PROVIDER: str = "gemini"
    CHAT_MODEL: str = "gemini-2.5-flash"

    # --- Extraction (cold path) ---
    EXTRACTION_PROVIDER: str = "gemini"
    EXTRACTION_MODEL: str = "gemini-2.5-flash"

    # --- Proactive + background jobs ---
    BACKGROUND_PROVIDER: str = "gemini"
    BACKGROUND_MODEL: str = "gemini-2.5-flash"

    # --- Embeddings ---
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSIONS: int = 768

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

    def api_key_for(self, provider: str) -> str:
        """Return the API key for a given provider name, or raise."""
        key_map = {
            "gemini": self.GOOGLE_API_KEY,
            "google": self.GOOGLE_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
        }
        key = key_map.get(provider.lower(), "")
        if not key:
            raise RuntimeError(
                f"No API key for provider '{provider}'. "
                f"Set {provider.upper()}_API_KEY in .env"
            )
        return key


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
    return s
