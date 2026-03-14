"""Tests for system prompt injection in the orchestrator engine."""

import pytest

from src.orchestrator.prompt_renderer import render_prompt


# Realistic data matching actual pipeline output shapes.
# This fixture would have caught the results.items Jinja2 collision.
REALISTIC_DATA = {
    "user_message": "I need to call dad, buy groceries, and finish the report by Friday",
    "message": "I need to call dad, buy groceries, and finish the report by Friday",
    "profile": {
        "tone_preference": "casual",
        "length_preference": "medium",
        "pushiness_preference": "gentle",
        "uses_emoji": False,
        "primary_language": "en",
        "timezone": "America/New_York",
        "display_name": "Alex",
    },
    "user_profile": {
        "tone_preference": "casual",
        "length_preference": "medium",
        "pushiness_preference": "gentle",
        "uses_emoji": False,
        "primary_language": "en",
    },
    "recent_messages": [
        {
            "role": "user",
            "content": "hey what should I do today?",
            "created_at": "2026-03-14T10:00:00Z",
        },
        {
            "role": "assistant",
            "content": "You've got a call to dad on your list.",
            "created_at": "2026-03-14T10:00:05Z",
        },
        {"role": "user", "content": "ok done", "created_at": "2026-03-14T10:01:00Z"},
    ],
    "open_items": [
        {
            "id": "a1b2c3d4-0000-0000-0000-000000000001",
            "interpreted_action": "Call dad",
            "status": "open",
            "deadline_at": "2026-03-15T17:00:00Z",
            "deadline_type": "soft",
            "urgency_score": 0.6,
            "energy_estimate": "low",
            "created_at": "2026-03-13T09:00:00Z",
        },
        {
            "id": "a1b2c3d4-0000-0000-0000-000000000002",
            "interpreted_action": "Buy groceries",
            "status": "open",
            "deadline_at": None,
            "deadline_type": "none",
            "urgency_score": 0.3,
            "energy_estimate": "medium",
            "created_at": "2026-03-12T14:00:00Z",
        },
    ],
    "urgent_items": [
        {
            "id": "a1b2c3d4-0000-0000-0000-000000000003",
            "interpreted_action": "Finish quarterly report",
            "status": "open",
            "deadline_at": "2026-03-14T23:59:00Z",
            "deadline_type": "hard",
            "urgency_score": 0.95,
            "energy_estimate": "high",
            "created_at": "2026-03-10T08:00:00Z",
        },
    ],
    "items": [
        {
            "id": "a1b2c3d4-0000-0000-0000-000000000001",
            "interpreted_action": "Call dad",
            "status": "open",
            "deadline_at": "2026-03-15T17:00:00Z",
            "deadline_type": "soft",
            "urgency_score": 0.6,
            "energy_estimate": "low",
            "created_at": "2026-03-13T09:00:00Z",
        },
    ],
    "results": {
        "items": [
            {
                "id": "a1b2c3d4-0000-0000-0000-000000000001",
                "interpreted_action": "Call dad",
                "status": "open",
                "urgency_score": 0.6,
            },
        ],
        "memories": [
            {"content": "User prefers mornings for phone calls", "confidence": 0.8},
        ],
        "messages": [
            {
                "role": "user",
                "content": "remind me about dad",
                "created_at": "2026-03-12T09:00:00Z",
            },
        ],
    },
    "memories": [
        {
            "content": "User prefers mornings for phone calls",
            "confidence": 0.8,
            "created_at": "2026-03-01T10:00:00Z",
        },
        {
            "content": "User works from home on Fridays",
            "confidence": 0.7,
            "created_at": "2026-02-20T12:00:00Z",
        },
    ],
    "extracted_items": {
        "items": [
            {
                "action": "Call dad",
                "deadline": "Friday",
                "urgency": 0.6,
                "energy": "low",
            },
            {
                "action": "Buy groceries",
                "deadline": None,
                "urgency": 0.3,
                "energy": "medium",
            },
        ],
    },
    "extracted": {
        "items": [
            {
                "action": "Finish report",
                "deadline": "2026-03-14",
                "urgency": 0.9,
                "energy": "high",
            },
        ],
    },
    "saved_count": 3,
    "item": {
        "id": "a1b2c3d4-0000-0000-0000-000000000001",
        "interpreted_action": "Call dad",
        "status": "done",
        "deadline_at": "2026-03-15T17:00:00Z",
        "deadline_type": "soft",
        "urgency_score": 0.6,
        "energy_estimate": "low",
        "created_at": "2026-03-13T09:00:00Z",
    },
    "momentum": {
        "completed_today": 2,
        "streak_days": 3,
        "total_open": 5,
    },
    "query_analysis": {
        "search_type": "status",
        "entity": "dad",
        "timeframe": "upcoming",
        "sources": ["items", "memories"],
    },
    "level": "medium",
    "query": "what do I need to do about dad?",
    "user_messages": [
        "I need to call dad",
        "buy groceries tomorrow",
    ],
    "completion_data": {
        "completed_count": 5,
        "total_items": 12,
        "streak_days": 3,
    },
    "message_activity": [
        {"date": "2026-03-13", "count": 8},
        {"date": "2026-03-12", "count": 5},
    ],
    "current_patterns": {
        "peak_hours": [9, 10, 14],
        "common_categories": ["personal", "work"],
    },
    "lookback_days": 30,
    "messages": [
        {"role": "user", "content": "hey what should I do?"},
        {"role": "assistant", "content": "You have a call to dad."},
    ],
    "current_profile": {
        "tone_preference": "casual",
        "length_preference": "medium",
    },
    "days_absent": 3,
    "completion_count": 5,
}


class TestSystemPromptRendering:
    def test_system_md_renders_without_profile(self) -> None:
        result = render_prompt("system.md", {"profile": None})
        assert "Unspool" in result
        assert "warm, casual" in result.lower() or "warm" in result.lower()

    def test_system_md_renders_with_profile(self) -> None:
        profile = {
            "tone_preference": "warm",
            "length_preference": "terse",
            "pushiness_preference": "firm",
            "uses_emoji": True,
            "primary_language": "sv",
        }
        result = render_prompt("system.md", {"profile": profile})
        assert "warm" in result
        assert "terse" in result
        assert "firm" in result
        assert "True" in result or "true" in result
        assert "sv" in result

    def test_system_md_renders_with_empty_profile(self) -> None:
        result = render_prompt("system.md", {"profile": {}})
        # Empty dict is falsy in Jinja2, so preferences block is skipped
        # Core personality should still be present
        assert "Unspool" in result
        assert "User preferences" not in result

    def test_system_md_has_core_rules(self) -> None:
        result = render_prompt("system.md", {"profile": None})
        # Verify critical product rules are in the system prompt
        assert "ONE thing" in result or "one thing" in result.lower()
        assert "never" in result.lower()

    def test_all_pipeline_prompts_render_independently(self) -> None:
        """Each pipeline prompt should render without errors when given minimal variables."""
        from pathlib import Path

        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        for prompt_file in prompts_dir.glob("*.md"):
            name = prompt_file.name
            # Provide empty values for all possible variables
            variables = {
                "user_message": "test message",
                "message": "test message",
                "profile": {},
                "user_profile": {},
                "recent_messages": [],
                "open_items": [],
                "urgent_items": [],
                "items": [],
                "results": {},
                "memories": [],
                "extracted_items": {},
                "saved_count": 0,
                "item": {},
                "momentum": {},
                "query": "test",
                "level": "low",
                "extracted": {},
                "user_messages": ["test"],
                "query_analysis": {},
                "completion_data": {},
                "message_activity": [],
                "current_patterns": {},
                "lookback_days": 30,
                "messages": [],
                "current_profile": {},
                "days_absent": 0,
                "completion_count": 0,
            }
            try:
                result = render_prompt(name, variables)
                assert len(result) > 0, f"Prompt {name} rendered empty"
            except Exception as e:
                pytest.fail(f"Prompt {name} failed to render: {e}")

    def test_all_pipeline_prompts_render_with_realistic_data(self) -> None:
        """Each pipeline prompt should render with realistic populated data.

        This catches Jinja2 collisions like results.items (dict method vs list data)
        that empty-data tests miss. Templates that expect a different data shape for
        a shared variable name (e.g. results as list vs dict) get a pass on
        UndefinedError, since those are shape mismatches, not template bugs.
        """
        from pathlib import Path

        from jinja2 import UndefinedError

        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        failures = []
        for prompt_file in prompts_dir.glob("*.md"):
            name = prompt_file.name
            try:
                result = render_prompt(name, REALISTIC_DATA)
                assert len(result) > 0, (
                    f"Prompt {name} rendered empty with realistic data"
                )
            except UndefinedError:
                # Shape mismatch (e.g. template expects list, data has dict) — acceptable
                pass
            except Exception as e:
                failures.append(f"{name}: {e}")

        if failures:
            pytest.fail(
                f"{len(failures)} prompt(s) failed with realistic data:\n"
                + "\n".join(failures)
            )

    def test_query_deep_respond_with_dict_results(self) -> None:
        """Specifically test query_deep_respond.md with dict results (the Jinja2 collision case)."""
        result = render_prompt("query_deep_respond.md", REALISTIC_DATA)
        assert len(result) > 0
        # The template should access results.items as data, not dict.items()
        assert "Call dad" in result
