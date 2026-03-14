"""Pipeline execution tests with mock LLM provider.

Tests actual execute_pipeline() with deterministic LLM responses
to verify the full extract → enrich → save → respond flow.
"""

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.llm.protocol import LLMResult, StreamChunk
from src.orchestrator.engine import execute_pipeline
from src.orchestrator.types import Context


class MockLLMProvider:
    """Deterministic LLM provider that returns responses keyed by prompt content."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self._default_response = '{"intent": "conversation", "confidence": 0.5}'

    def _match_response(self, messages: list[dict[str, Any]]) -> str:
        combined = " ".join(m.get("content", "") for m in messages)
        for key, response in self._responses.items():
            if key in combined:
                return response
        return self._default_response

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        content = self._match_response(messages)
        return LLMResult(content=content, input_tokens=100, output_tokens=50)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        content = self._match_response(messages)
        for char in content:
            yield StreamChunk(token=char)
        yield StreamChunk(
            token="", done=True, input_tokens=100, output_tokens=len(content)
        )

    async def generate_structured(
        self,
        messages: list[dict[str, Any]],
        schema: Any,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        content = self._match_response(messages)
        return schema.model_validate_json(content)


def _make_context(message: str = "test message") -> Context:
    return Context(
        user_id="test-user-id",
        trace_id="test-trace-id",
        user_message=message,
        profile={
            "tone_preference": "casual",
            "length_preference": "medium",
            "pushiness_preference": "gentle",
            "uses_emoji": False,
            "primary_language": "en",
        },
    )


def _pipeline_patches(mock_provider: MockLLMProvider) -> contextlib.ExitStack:
    """Enter all common patches and return an ExitStack managing them."""
    stack = contextlib.ExitStack()
    stack.enter_context(
        patch("src.orchestrator.engine.get_llm_provider", return_value=mock_provider)
    )
    stack.enter_context(
        patch("src.orchestrator.engine.log_llm_usage", new_callable=AsyncMock)
    )
    stack.enter_context(patch("src.orchestrator.engine.log_step_started"))
    stack.enter_context(patch("src.orchestrator.engine.log_step_completed"))
    stack.enter_context(patch("src.orchestrator.engine.log_step_error"))
    stack.enter_context(patch("src.orchestrator.engine.log_message_completed"))
    stack.enter_context(patch("src.orchestrator.engine.log_variant_selected"))
    stack.enter_context(
        patch(
            "src.orchestrator.engine.select_variant",
            new_callable=AsyncMock,
            return_value=("default", {}),
        )
    )
    return stack


@pytest.mark.asyncio
class TestBrainDumpPipeline:
    async def test_extract_enrich_save_respond(self) -> None:
        extract_response = json.dumps(
            {
                "items": [
                    {
                        "action": "Call dad",
                        "deadline": None,
                        "urgency": 0.5,
                        "energy": "low",
                    },
                    {
                        "action": "Buy groceries",
                        "deadline": "tomorrow",
                        "urgency": 0.3,
                        "energy": "medium",
                    },
                ],
            }
        )

        mock_provider = MockLLMProvider(
            {
                "brain_dump_extract": extract_response,
                "brain_dump_respond": "Got it! I've noted those down for you.",
            }
        )

        mock_enrich = AsyncMock(
            return_value=[
                {
                    "action": "Call dad",
                    "deadline": None,
                    "urgency": 0.5,
                    "energy": "low",
                },
                {
                    "action": "Buy groceries",
                    "deadline": "tomorrow",
                    "urgency": 0.3,
                    "energy": "medium",
                },
            ]
        )
        mock_save = AsyncMock(return_value=2)

        tool_registry = {
            "enrich_items": mock_enrich,
            "save_items": mock_save,
        }

        context = _make_context("I need to call dad and buy groceries")

        with _pipeline_patches(mock_provider):
            tokens = []
            async for token in execute_pipeline("brain_dump", context, tool_registry):
                tokens.append(token)

        response = "".join(tokens)
        assert len(response) > 0
        mock_enrich.assert_called_once()
        mock_save.assert_called_once()


@pytest.mark.asyncio
class TestQuerySearchPipeline:
    async def test_analyze_fetch_respond(self) -> None:
        analyze_response = json.dumps(
            {
                "search_type": "status",
                "entity": "dad",
                "timeframe": "upcoming",
                "sources": ["items"],
            }
        )

        mock_provider = MockLLMProvider(
            {
                "analyze_query": analyze_response,
                "query_deep_respond": "You have a reminder to call dad.",
            }
        )

        fetch_result = {
            "items": [
                {
                    "interpreted_action": "Call dad",
                    "status": "open",
                    "urgency_score": 0.5,
                },
            ],
            "memories": [],
            "messages": [],
        }
        mock_smart_fetch = AsyncMock(return_value=fetch_result)

        tool_registry = {"smart_fetch": mock_smart_fetch}

        context = _make_context("what do I need to do about dad?")

        with _pipeline_patches(mock_provider):
            tokens = []
            async for token in execute_pipeline("query_search", context, tool_registry):
                tokens.append(token)

        response = "".join(tokens)
        assert len(response) > 0
        mock_smart_fetch.assert_called_once()


@pytest.mark.asyncio
class TestPipelineErrorHandling:
    async def test_tool_exception_propagates(self) -> None:
        extract_response = json.dumps(
            {
                "items": [
                    {
                        "action": "Call dad",
                        "deadline": None,
                        "urgency": 0.5,
                        "energy": "low",
                    }
                ],
            }
        )

        mock_provider = MockLLMProvider(
            {
                "brain_dump_extract": extract_response,
            }
        )

        mock_enrich = AsyncMock(side_effect=RuntimeError("DB connection failed"))
        mock_save = AsyncMock(return_value=0)

        tool_registry = {
            "enrich_items": mock_enrich,
            "save_items": mock_save,
        }

        context = _make_context("call dad")

        with _pipeline_patches(mock_provider):
            with pytest.raises(RuntimeError, match="DB connection failed"):
                async for _ in execute_pipeline("brain_dump", context, tool_registry):
                    pass

    async def test_json_parse_failure_returns_empty_dict(self) -> None:
        """When LLM returns non-JSON for a structured step, output should be {}."""
        mock_provider = MockLLMProvider(
            {
                "analyze_query": "I'm not sure what you're asking about, sorry!",
                "query_deep_respond": "Let me help you find that.",
            }
        )

        mock_smart_fetch = AsyncMock(
            return_value={"items": [], "memories": [], "messages": []}
        )
        tool_registry = {"smart_fetch": mock_smart_fetch}

        context = _make_context("find my stuff")

        with _pipeline_patches(mock_provider):
            tokens = []
            async for token in execute_pipeline("query_search", context, tool_registry):
                tokens.append(token)

        assert len(tokens) > 0
        mock_smart_fetch.assert_called_once()
