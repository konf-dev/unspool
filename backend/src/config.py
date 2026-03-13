from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_JWT_SIGNING_SECRET: str = ""

    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""

    QSTASH_TOKEN: str = ""
    QSTASH_CURRENT_SIGNING_KEY: str = ""
    QSTASH_NEXT_SIGNING_KEY: str = ""

    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_MODEL_FAST: str = ""
    LLM_PROVIDER: str = "anthropic"

    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_PROVIDER: str = "openai"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    DATABASE_URL: str = ""

    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    API_URL: str = "http://localhost:8000"

    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.ENVIRONMENT != "development":
        missing = [
            name
            for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_JWT_SIGNING_SECRET", "DATABASE_URL")
            if not getattr(settings, name)
        ]
        if missing:
            raise RuntimeError(f"Missing required config in {settings.ENVIRONMENT}: {', '.join(missing)}")
    return settings
