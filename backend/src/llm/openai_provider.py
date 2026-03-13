from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.config import get_settings
from src.llm.protocol import LLMResult, StreamChunk
from src.telemetry.logger import get_logger

_log = get_logger("llm.openai")


class OpenAIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.LLM_API_KEY)
        self._default_model = default_model or settings.LLM_MODEL

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
            **kwargs,
        )
        choice = response.choices[0]
        return LLMResult(
            content=choice.message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield StreamChunk(token=chunk.choices[0].delta.content)

            if chunk.usage:
                yield StreamChunk(
                    token="",
                    done=True,
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                )

    async def generate_structured(
        self,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        response = await self._client.beta.chat.completions.parse(
            model=model or self._default_model,
            messages=messages,
            response_format=schema,
            **kwargs,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        return parsed
