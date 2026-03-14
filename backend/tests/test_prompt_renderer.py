import pytest

from src.orchestrator.prompt_renderer import render_prompt


class TestFrontmatterStripping:
    def test_frontmatter_not_in_output(self) -> None:
        result = render_prompt(
            "classify_intent.md",
            {"user_message": "test", "recent_messages": []},
        )
        assert "input_vars" not in result
        assert "---" not in result


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

    def test_user_input_tags_present(self) -> None:
        result = render_prompt(
            "classify_intent.md",
            {
                "user_message": "test injection",
                "recent_messages": [],
            },
        )
        assert "<user_input>test injection</user_input>" in result

    def test_missing_template_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            render_prompt("nonexistent_template_xyz.md", {})
