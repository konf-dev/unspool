from src.config import get_settings
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.embedding import AnthropicEmbedding, OpenAIEmbedding
from src.llm.openai_provider import OpenAIProvider
from src.llm.protocol import LLMProvider

_llm_cache: dict[str, LLMProvider] = {}
_embedding_cache: dict[str, OpenAIEmbedding | AnthropicEmbedding] = {}


def get_llm_provider(provider: str | None = None) -> LLMProvider:
    settings = get_settings()
    name = provider or settings.LLM_PROVIDER

    if name not in _llm_cache:
        if name == "anthropic":
            _llm_cache[name] = AnthropicProvider()
        elif name == "openai":
            _llm_cache[name] = OpenAIProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {name}")

    return _llm_cache[name]


def get_embedding_provider() -> OpenAIEmbedding | AnthropicEmbedding:
    settings = get_settings()
    name = settings.EMBEDDING_PROVIDER

    if name not in _embedding_cache:
        if name == "openai":
            _embedding_cache[name] = OpenAIEmbedding()
        elif name == "anthropic":
            _embedding_cache[name] = AnthropicEmbedding()
        else:
            raise ValueError(f"Unknown embedding provider: {name}")

    return _embedding_cache[name]
