"""Tests for system prompt injection in the orchestrator engine."""
import pytest

from src.orchestrator.prompt_renderer import render_prompt


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
        import os
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
