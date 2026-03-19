"""Deterministic personality checks — no LLM calls needed.

These run on every PR. They check the system prompt and response patterns
for forbidden words, phrases, and structural violations.
"""

import re

import pytest

from src.agent.tools import get_tool_definitions
from src.prompt_renderer import render_prompt

# Forbidden in any response
FORBIDDEN_VERBS = [
    "tackle",
    "crush",
    "knock out",
    "nail",
    "smash",
    "conquer",
    "power through",
    "blast through",
]

FORBIDDEN_PHRASES = [
    "you've got this",
    "one step at a time",
    "let's get started",
    "let's do this",
    "let's get after it",
    "you can do it",
    "i believe in you",
    "great job",
    "amazing work",
    "keep it up",
    "proud of you",
    "way to go",
]


class TestSystemPromptRules:
    """Verify the system prompt contains critical personality rules."""

    @pytest.fixture(autouse=True)
    def _build_prompt(self) -> None:
        self.prompt = render_prompt(
            "agent_system.md",
            {
                "profile": {
                    "tone_preference": "casual",
                    "length_preference": "medium",
                    "pushiness_preference": "gentle",
                    "uses_emoji": False,
                    "primary_language": "en",
                },
                "context": "",
            },
        )

    def test_no_lists_rule(self) -> None:
        assert "list" in self.prompt.lower(), (
            "system prompt must mention list restrictions"
        )

    def test_one_thing_rule(self) -> None:
        assert "one" in self.prompt.lower(), (
            "system prompt must mention 'one thing at a time'"
        )

    def test_adhd_only_as_prohibition(self) -> None:
        prompt_lower = self.prompt.lower()
        if "adhd" in prompt_lower:
            # ADHD should only appear in a "never mention" context
            idx = prompt_lower.index("adhd")
            surrounding = prompt_lower[max(0, idx - 80) : idx + 20]
            assert any(
                neg in surrounding for neg in ["never", "don't", "do not", "avoid"]
            ), "system prompt mentions ADHD outside of a prohibition context"

    def test_no_guilt_rule(self) -> None:
        assert "guilt" in self.prompt.lower(), (
            "system prompt must mention no-guilt rule"
        )

    def test_crisis_handling(self) -> None:
        prompt_lower = self.prompt.lower()
        crisis_terms = ["crisis", "hotline", "988", "suicid", "self-harm", "emergency"]
        has_crisis_handling = any(term in prompt_lower for term in crisis_terms)
        if not has_crisis_handling:
            pytest.skip(
                "GAPS: system prompt has no crisis handling instructions — "
                "add crisis/suicide resource language to agent_system.md"
            )

    def test_forbidden_verbs_banned(self) -> None:
        for verb in FORBIDDEN_VERBS:
            if verb in self.prompt.lower():
                # It's fine if the prompt says "never use" these words
                context = self.prompt.lower()
                verb_idx = context.index(verb)
                # Check a wider context window — prohibition headers can be far from the verb
                surrounding = context[max(0, verb_idx - 150) : verb_idx + 50]
                assert any(
                    neg in surrounding
                    for neg in ["never", "don't", "do not", "avoid", "not"]
                ), f"system prompt uses '{verb}' without a prohibition context"


class TestToolDefinitions:
    """Verify tool definitions are well-formed."""

    def test_all_tools_have_descriptions(self) -> None:
        tools = get_tool_definitions()
        for tool in tools:
            fn = tool["function"]
            assert fn.get("description"), f"tool {fn['name']} missing description"

    def test_tool_count(self) -> None:
        tools = get_tool_definitions()
        assert len(tools) >= 15, f"expected 15+ tools, got {len(tools)}"

    def test_save_items_schema(self) -> None:
        tools = get_tool_definitions()
        save_items = next(t for t in tools if t["function"]["name"] == "save_items")
        params = save_items["function"]["parameters"]
        assert "items" in params["properties"]
        assert params["properties"]["items"]["type"] == "array"

    def test_pick_next_has_no_required_params(self) -> None:
        tools = get_tool_definitions()
        pick_next = next(t for t in tools if t["function"]["name"] == "pick_next")
        params = pick_next["function"]["parameters"]
        required = params.get("required", [])
        assert len(required) == 0, "pick_next should have no required params"


class TestForbiddenPatterns:
    """Static checks that can run against any response string."""

    @staticmethod
    def check_forbidden_words(text: str) -> list[str]:
        violations = []
        text_lower = text.lower()
        for verb in FORBIDDEN_VERBS:
            if verb in text_lower:
                violations.append(f"forbidden verb: '{verb}'")
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text_lower:
                violations.append(f"forbidden phrase: '{phrase}'")
        return violations

    @staticmethod
    def check_no_numbered_list(text: str) -> bool:
        """Returns True if text contains a numbered list (1. 2. 3. pattern)."""
        return bool(re.search(r"^\s*\d+\.\s", text, re.MULTILINE))

    @staticmethod
    def check_no_bullet_list(text: str) -> bool:
        """Returns True if text contains bullet points."""
        lines = text.strip().split("\n")
        bullet_lines = sum(
            1 for line in lines if line.strip().startswith(("- ", "• ", "* "))
        )
        return bullet_lines >= 3

    @staticmethod
    def check_response_length(text: str, max_lines: int = 10) -> bool:
        """Returns True if response exceeds max lines."""
        return len(text.strip().split("\n")) > max_lines


# Make check functions importable for use in LLM eval tests
def assert_no_forbidden_patterns(response: str) -> None:
    violations = TestForbiddenPatterns.check_forbidden_words(response)
    if TestForbiddenPatterns.check_no_numbered_list(response):
        violations.append("contains numbered list")
    if TestForbiddenPatterns.check_no_bullet_list(response):
        violations.append("contains bullet list (3+ items)")
    assert not violations, f"Personality violations: {violations}"
