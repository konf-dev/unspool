import json
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from src.config import get_settings
from src.llm.protocol import LLMResult, StreamChunk
from src.telemetry.logger import get_logger

_log = get_logger("llm.anthropic")


class AnthropicProvider:
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=api_key or settings.LLM_API_KEY)
        self._default_model = default_model or settings.LLM_MODEL

    def _split_system(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system = None
        filtered = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg["content"]
            else:
                filtered.append(msg)
        return system, filtered

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        system, msgs = self._split_system(messages)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": msgs,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            **kwargs,
        }
        if system:
            params["system"] = system

        response = await self._client.messages.create(**params)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResult(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        system, msgs = self._split_system(messages)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": msgs,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            **kwargs,
        }
        if system:
            params["system"] = system

        async with self._client.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(token=text)

            final = await stream.get_final_message()
            yield StreamChunk(
                token="",
                done=True,
                input_tokens=final.usage.input_tokens,
                output_tokens=final.usage.output_tokens,
            )

    async def generate_structured(
        self,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system, msgs = self._split_system(messages)

        augmented_system = (system or "") + (
            f"\n\nRespond with valid JSON matching this schema:\n{schema_json}\n"
            "Return ONLY the JSON object, no other text."
        )

        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": msgs,
            "system": augmented_system.strip(),
            "max_tokens": kwargs.pop("max_tokens", 4096),
            **kwargs,
        }

        response = await self._client.messages.create(**params)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return schema.model_validate_json(content)
