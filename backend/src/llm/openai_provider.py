from typing import Any, AsyncIterator, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from src.agent.types import StreamEvent
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
            messages=cast(list[ChatCompletionMessageParam], messages),
            **kwargs,
        )
        if not response.choices:
            _log.warning("openai.empty_choices")
            return LLMResult(content="", input_tokens=0, output_tokens=0)
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
            messages=cast(list[ChatCompletionMessageParam], messages),
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
            messages=cast(list[ChatCompletionMessageParam], messages),
            response_format=schema,
            **kwargs,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        return parsed

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        from openai.types.chat import ChatCompletionToolParam
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            tools=cast(list[ChatCompletionToolParam], tools),
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )

        # Accumulate tool calls across chunks
        tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in response:
            if chunk.choices:
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    yield StreamEvent(type="text_delta", content=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name
                                if tc_delta.function and tc_delta.function.name
                                else "",
                                "arguments": "",
                            }
                            if tool_calls[idx]["name"]:
                                yield StreamEvent(
                                    type="tool_call_start",
                                    tool_call_id=tool_calls[idx]["id"],
                                    tool_name=tool_calls[idx]["name"],
                                )

                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments
                            yield StreamEvent(
                                type="tool_call_delta",
                                tool_call_id=tool_calls[idx]["id"],
                                arguments_delta=tc_delta.function.arguments,
                            )

                if choice.finish_reason == "tool_calls":
                    for tc in tool_calls.values():
                        yield StreamEvent(
                            type="tool_call_done",
                            tool_call_id=tc["id"],
                            tool_name=tc["name"],
                            arguments_delta=tc["arguments"],
                        )
                    tool_calls = {}

            if chunk.usage:
                yield StreamEvent(
                    type="done",
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                )
