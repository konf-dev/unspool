import pytest

from src.orchestrator.prompt_renderer import render_prompt, _strip_frontmatter


class TestStripFrontmatter:
    def test_with_frontmatter(self) -> None:
        source = "---\nname: test\n---\nHello {{ name }}"
        result = _strip_frontmatter(source)
        assert result == "Hello {{ name }}"

    def test_without_frontmatter(self) -> None:
        source = "Hello {{ name }}"
        result = _strip_frontmatter(source)
        assert result == "Hello {{ name }}"

    def test_empty_frontmatter(self) -> None:
        source = "---\n---\nBody here"
        result = _strip_frontmatter(source)
        assert result == "Body here"


class TestRenderPrompt:
    def test_classify_intent_renders(self) -> None:
        result = render_prompt(
            "classify_intent.md",
            {
                "user_message": "I need to buy groceries",
                "recent_messages": [],
            },
        )
        assert "I need to buy groceries" in result
        assert "brain_dump" in result

    def test_classify_intent_with_history(self) -> None:
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = render_prompt(
            "classify_intent.md",
            {
                "user_message": "done with that",
                "recent_messages": messages,
            },
        )
        assert "hello" in result
        assert "hi there" in result

    def test_missing_template_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            render_prompt("nonexistent_template_xyz.md", {})
