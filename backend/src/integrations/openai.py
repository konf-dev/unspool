"""Shared OpenAI client — single connection pool, auto-instrumented by Langfuse.

When Langfuse is configured, uses ``langfuse.openai.AsyncOpenAI`` which is a
drop-in replacement that automatically logs every completion and embedding call
(input, output, tokens, latency, model) to Langfuse without any extra code.

When Langfuse is NOT configured, falls back to the plain ``openai.AsyncOpenAI``.
"""

from src.core.settings import get_settings
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("integrations.openai")

_client = None


def get_openai_client():
    """Return the process-wide AsyncOpenAI client, creating it on first call.

    If Langfuse is configured, this returns ``langfuse.openai.AsyncOpenAI``
    which auto-traces every call.  Otherwise plain ``openai.AsyncOpenAI``.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError(
            "No OpenAI API key configured. Set LLM_API_KEY or OPENAI_API_KEY."
        )

    # Try Langfuse-wrapped client first (auto-instruments all calls)
    if settings.LANGFUSE_HOST and settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        try:
            from langfuse.openai import AsyncOpenAI  # type: ignore[import-untyped]
            _client = AsyncOpenAI(api_key=api_key)
            _log.info("openai.client_initialized", langfuse_instrumented=True)
            return _client
        except ImportError:
            _log.debug("openai.langfuse_wrapper_unavailable")

    # Fallback to plain OpenAI client
    from openai import AsyncOpenAI
    _client = AsyncOpenAI(api_key=api_key)
    _log.info("openai.client_initialized", langfuse_instrumented=False)
    return _client


@observe(name="embedding")
async def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector for *text* using the configured model."""
    settings = get_settings()
    client = get_openai_client()
    response = await client.embeddings.create(
        input=text,
        model=settings.EMBEDDING_MODEL,
    )
    return response.data[0].embedding
