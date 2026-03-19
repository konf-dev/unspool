import pytest

from src.prompt_renderer import render_prompt


class TestFrontmatterStripping:
    def test_frontmatter_not_in_output(self) -> None:
        result = render_prompt(
            "agent_system.md",
            {"profile": None, "context": ""},
        )
        assert "input_vars" not in result
        assert result.count("---") == 0


class TestRenderPrompt:
    def test_agent_system_renders(self) -> None:
        result = render_prompt(
            "agent_system.md",
            {
                "profile": {"tone_preference": "warm"},
                "context": "<context>test</context>",
            },
        )
        assert "Unspool" in result
        assert "warm" in result
        assert "<context>test</context>" in result

    def test_agent_system_without_profile(self) -> None:
        result = render_prompt(
            "agent_system.md",
            {"profile": None, "context": ""},
        )
        assert "Unspool" in result
        assert "Tone:" not in result

    def test_missing_template_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            render_prompt("nonexistent_template_xyz.md", {})

    def test_agent_system_renders_basic(self) -> None:
        result = render_prompt("agent_system.md", {"profile": None, "context": ""})
        assert "Unspool" in result
