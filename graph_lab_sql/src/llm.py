"""LLM provider abstraction — Anthropic + OpenAI + Ollama."""

import json
from collections.abc import AsyncIterator

import structlog
from anthropic import AsyncAnthropic
from graph_lab_sql.src.config import (
    LLM_API_KEY,
    LLM_MODEL,
    OLLAMA_URL,
    OPENAI_API_KEY,
)
from openai import AsyncOpenAI

logger = structlog.get_logger()

_anthropic: AsyncAnthropic | None = None
_openai: AsyncOpenAI | None = None
_ollama: AsyncOpenAI | None = None


def _get_anthropic() -> AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = AsyncAnthropic(api_key=LLM_API_KEY)
    return _anthropic


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai


def _get_ollama() -> AsyncOpenAI:
    global _ollama
    if _ollama is None:
        _ollama = AsyncOpenAI(base_url=f"{OLLAMA_URL}/v1", api_key="ollama")
    return _ollama


def _route(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt-", "o1", "o3", "text-embedding")):
        return "openai"
    return "ollama"


async def generate(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    model = model or LLM_MODEL
    provider = _route(model)

    if provider == "anthropic":
        return await _anthropic_generate(
            messages, model, system, temperature, max_tokens
        )
    if provider == "ollama":
        return await _ollama_generate(messages, model, system, temperature, max_tokens)
    return await _openai_generate(messages, model, system, temperature, max_tokens)


async def generate_json(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict:
    model = model or LLM_MODEL
    provider = _route(model)

    if provider == "ollama":
        return await _ollama_generate_json(
            messages, model, system, temperature, max_tokens
        )

    raw = await generate(messages, model, system, temperature, max_tokens)
    return _parse_json(raw)


async def stream(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    model = model or LLM_MODEL
    provider = _route(model)

    if provider == "anthropic":
        async for token in _anthropic_stream(
            messages, model, system, temperature, max_tokens
        ):
            yield token
    elif provider == "ollama":
        async for token in _ollama_stream(
            messages, model, system, temperature, max_tokens
        ):
            yield token
    else:
        async for token in _openai_stream(
            messages, model, system, temperature, max_tokens
        ):
            yield token


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("json_parse_error", error=str(e), raw_text=text[:200])
        raise


# --- Anthropic ---


async def _anthropic_generate(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    client = _get_anthropic()
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        kwargs["system"] = system
    response = await client.messages.create(**kwargs)
    return response.content[0].text


async def _anthropic_stream(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    client = _get_anthropic()
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as resp:
        async for text in resp.text_stream:
            yield text


# --- OpenAI ---


async def _openai_generate(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    client = _get_openai()
    msgs = _build_openai_messages(messages, system)
    response = await client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def _openai_stream(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    client = _get_openai()
    msgs = _build_openai_messages(messages, system)
    resp = await client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in resp:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# --- Ollama (OpenAI-compatible API) ---


async def _ollama_generate(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    client = _get_ollama()
    msgs = _build_openai_messages(messages, system)
    response = await client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def _ollama_generate_json(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> dict:
    client = _get_ollama()
    msgs = _build_openai_messages(messages, system)
    response = await client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    return _parse_json(raw)


async def _ollama_stream(
    messages: list[dict],
    model: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    client = _get_ollama()
    msgs = _build_openai_messages(messages, system)
    resp = await client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in resp:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def _build_openai_messages(messages: list[dict], system: str | None) -> list[dict]:
    result = []
    if system:
        result.append({"role": "system", "content": system})
    result.extend(messages)
    return result
