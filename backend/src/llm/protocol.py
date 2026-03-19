from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from pydantic import BaseModel

from src.agent.types import StreamEvent


@dataclass
class LLMResult:
    content: str
    input_tokens: int
    output_tokens: int


@dataclass
class StreamChunk:
    token: str
    done: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResult: ...

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]: ...

    async def generate_structured(
        self,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseModel: ...

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
