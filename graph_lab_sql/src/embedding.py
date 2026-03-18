"""Embedding generation — OpenAI API or Ollama local."""

import structlog
from graph_lab_sql.src.config import EMBEDDING_MODEL, OLLAMA_URL, OPENAI_API_KEY
from openai import AsyncOpenAI

logger = structlog.get_logger()

_openai_client: AsyncOpenAI | None = None
_ollama_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _get_ollama() -> AsyncOpenAI:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = AsyncOpenAI(base_url=f"{OLLAMA_URL}/v1", api_key="ollama")
    return _ollama_client


def _is_local_model(model: str) -> bool:
    return model.startswith(("nomic-", "mxbai-", "all-minilm", "snowflake-"))


async def generate_embedding(text: str, model: str | None = None) -> list[float]:
    model = model or EMBEDDING_MODEL
    client = _get_ollama() if _is_local_model(model) else _get_openai()
    response = await client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


async def generate_embeddings_batch(
    texts: list[str], model: str | None = None
) -> list[list[float]]:
    if not texts:
        return []
    model = model or EMBEDDING_MODEL
    client = _get_ollama() if _is_local_model(model) else _get_openai()
    response = await client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
