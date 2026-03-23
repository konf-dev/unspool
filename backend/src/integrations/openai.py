"""Shared OpenAI client — single connection pool for the entire process.

Every module that needs embeddings or completions imports from here instead of
constructing its own AsyncOpenAI instance.  The client is created lazily on first
access so that import-time side effects are zero (important for tests).
"""

from openai import AsyncOpenAI

from src.core.settings import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("integrations.openai")

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return the process-wide AsyncOpenAI client, creating it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "No OpenAI API key configured. Set LLM_API_KEY or OPENAI_API_KEY."
            )
        _client = AsyncOpenAI(api_key=api_key)
        _log.info("openai.client_initialized")
    return _client


async def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector for *text* using the configured model."""
    settings = get_settings()
    client = get_openai_client()
    response = await client.embeddings.create(
        input=text,
        model=settings.EMBEDDING_MODEL,
    )
    return response.data[0].embedding
