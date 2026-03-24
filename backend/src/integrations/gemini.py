"""Google Gemini client — used for direct SDK calls (structured outputs, embeddings).

The LangChain integration (``langchain-google-genai``) is used separately in the
hot path for tool-calling via ``ChatGoogleGenerativeAI`` — see graph.py.

Embedding guidelines (from https://ai.google.dev/gemini-api/docs/embeddings):
- Use task_type to optimize embeddings for the intended relationship:
    RETRIEVAL_DOCUMENT  — when storing/indexing content
    RETRIEVAL_QUERY     — when searching for content
    SEMANTIC_SIMILARITY — when comparing two pieces of content
- At dimensions < 3072, embeddings must be L2-normalized for accurate cosine similarity.
- Recommended dimensions: 768, 1536, or 3072.
"""

import math

from google import genai
from google.genai import types

from src.core.settings import get_settings
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("integrations.gemini")

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Return the process-wide genai Client, creating it on first call."""
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    api_key = settings.api_key_for("gemini")
    _client = genai.Client(api_key=api_key)
    _log.info("gemini.client_initialized")
    return _client


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector. Required for Gemini embeddings at < 3072 dims.

    See: https://ai.google.dev/gemini-api/docs/embeddings
    "For output dimensionality other than 3072, you need to normalize the embeddings"
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


@observe(name="embedding")
async def get_embedding(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[float]:
    """Generate an embedding vector for *text* using the configured embedding model.

    Args:
        text: The text to embed.
        task_type: Gemini embedding task type. Use:
            - "RETRIEVAL_DOCUMENT" when storing/indexing nodes (cold path)
            - "RETRIEVAL_QUERY" when searching for nodes (hot path, context assembly)
            - "SEMANTIC_SIMILARITY" when comparing content (dedup matching)
            See: https://ai.google.dev/gemini-api/docs/embeddings
    """
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    settings = get_settings()
    client = get_gemini_client()
    result = await client.aio.models.embed_content(
        model=settings.EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.EMBEDDING_DIMENSIONS,
        ),
    )
    return _l2_normalize(list(result.embeddings[0].values))


@observe(name="embedding.batch")
async def get_embeddings_batch(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Embed multiple texts in a single API call.

    More efficient than calling get_embedding() in a loop — one HTTP round trip
    instead of N.  See: https://ai.google.dev/gemini-api/docs/embeddings
    """
    if not texts:
        return []
    # Filter out empty strings — Gemini rejects empty Parts
    valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
    valid_texts = [texts[i] for i in valid_indices]
    if not valid_texts:
        return [[] for _ in texts]
    settings = get_settings()
    client = get_gemini_client()
    result = await client.aio.models.embed_content(
        model=settings.EMBEDDING_MODEL,
        contents=valid_texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.EMBEDDING_DIMENSIONS,
        ),
    )
    valid_embeddings = [_l2_normalize(list(e.values)) for e in result.embeddings]
    # Reconstruct full list with empty lists for filtered-out texts
    out: list[list[float]] = [[] for _ in texts]
    for idx, emb in zip(valid_indices, valid_embeddings):
        out[idx] = emb
    return out
