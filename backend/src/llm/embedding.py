from openai import AsyncOpenAI

from src.config import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("llm.embedding")


class OpenAIEmbedding:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.EMBEDDING_API_KEY)
        self._model = model or settings.EMBEDDING_MODEL

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]


class AnthropicEmbedding:
    """Stub — Anthropic does not yet offer an embeddings API."""

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Anthropic embeddings not available")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Anthropic embeddings not available")
