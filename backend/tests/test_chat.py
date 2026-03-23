"""Tests for chat endpoint."""

import pytest
from unittest.mock import patch, AsyncMock


class TestChatRequest:
    def test_request_validation(self):
        """ChatRequest validates fields."""
        from src.api.chat import ChatRequest

        # Valid request
        req = ChatRequest(message="hello", session_id="sess-1")
        assert req.message == "hello"
        assert req.timezone is None

        # With timezone
        req = ChatRequest(message="hi", session_id="s", timezone="America/New_York")
        assert req.timezone == "America/New_York"

    def test_empty_message_rejected(self):
        """Empty message should fail validation."""
        from src.api.chat import ChatRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ChatRequest(message="", session_id="s")


class TestConfigLoader:
    def test_loads_gate_config(self):
        """gate.yaml loads correctly."""
        from src.core.config_loader import load_config

        config = load_config("gate")
        assert "rate_limits" in config
        assert "free" in config["rate_limits"]

    def test_loads_proactive_config(self):
        """proactive.yaml loads correctly."""
        from src.core.config_loader import load_config

        config = load_config("proactive")
        assert "triggers" in config
        assert "deadline_imminent" in config["triggers"]

    def test_missing_config_raises(self):
        """Missing config raises FileNotFoundError."""
        from src.core.config_loader import load_config

        with pytest.raises(FileNotFoundError):
            load_config("nonexistent_config")


class TestPromptRenderer:
    def test_renders_agent_system(self):
        """agent_system.md renders with variables."""
        from src.core.prompt_renderer import render_prompt

        result = render_prompt("agent_system.md", {
            "profile": {"tone_preference": "casual", "uses_emoji": False},
            "context": "<context>test</context>",
            "current_time": "Monday, March 23, 2026 at 10:00 (UTC)",
        })
        assert "Unspool" in result
        assert "casual" in result
        assert "<context>test</context>" in result

    def test_escapes_user_input(self):
        """User input with Jinja2 syntax is escaped."""
        from src.core.prompt_renderer import _escape_user_input

        escaped = _escape_user_input("test {{ dangerous }} content")
        assert "{{" not in escaped
        assert "{ {" in escaped
