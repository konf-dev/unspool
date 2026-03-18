"""Tests for _extract_json() from engine.py — covers all LLM output patterns seen in production."""

from src.orchestrator.engine import _extract_json


class TestExtractJsonClean:
    def test_clean_object(self) -> None:
        result = _extract_json('{"intent": "brain_dump", "confidence": 0.9}', "test")
        assert result == {"intent": "brain_dump", "confidence": 0.9}

    def test_clean_array(self) -> None:
        result = _extract_json('[{"item": "call dad"}, {"item": "buy milk"}]', "test")
        assert len(result) == 2
        assert result[0]["item"] == "call dad"

    def test_clean_with_whitespace(self) -> None:
        result = _extract_json('  \n {"key": "value"} \n  ', "test")
        assert result == {"key": "value"}


class TestExtractJsonCodeFenced:
    def test_json_code_fence(self) -> None:
        content = '```json\n{"items": [{"action": "call dad"}]}\n```'
        result = _extract_json(content, "test")
        assert result == {"items": [{"action": "call dad"}]}

    def test_plain_code_fence(self) -> None:
        content = '```\n{"status": "done"}\n```'
        result = _extract_json(content, "test")
        assert result == {"status": "done"}

    def test_code_fence_with_surrounding_text(self) -> None:
        content = (
            "Here's the extracted data:\n"
            "```json\n"
            '{"items": [{"action": "buy groceries", "urgency": 0.5}]}\n'
            "```\n"
            "Let me know if you need anything else."
        )
        result = _extract_json(content, "test")
        assert result["items"][0]["action"] == "buy groceries"


class TestExtractJsonTextBeforeAfter:
    def test_text_before_json(self) -> None:
        content = (
            'Sure! Here\'s the result: {"intent": "query_search", "confidence": 0.85}'
        )
        result = _extract_json(content, "test")
        assert result["intent"] == "query_search"

    def test_text_before_and_after_falls_back(self) -> None:
        # Current implementation can't parse JSON with trailing text (no closing delimiter scan).
        # This documents the limitation — extraction returns a parse error marker.
        content = (
            'I analyzed your message. {"search_type": "status", "entity": null} '
            "Hope that helps!"
        )
        result = _extract_json(content, "test")
        assert result["_parse_error"] is True

    def test_text_before_json_at_end(self) -> None:
        # But text before JSON with nothing after works fine.
        content = 'I analyzed your message. {"search_type": "status", "entity": null}'
        result = _extract_json(content, "test")
        assert result["search_type"] == "status"

    def test_text_before_array(self) -> None:
        content = 'Here are the items: [{"action": "call mom"}]'
        result = _extract_json(content, "test")
        assert len(result) == 1


class TestExtractJsonNested:
    def test_nested_objects(self) -> None:
        content = '{"query": {"type": "status", "filters": {"status": "open"}}}'
        result = _extract_json(content, "test")
        assert result["query"]["filters"]["status"] == "open"

    def test_nested_arrays(self) -> None:
        content = '{"items": [{"tags": ["urgent", "work"]}]}'
        result = _extract_json(content, "test")
        assert result["items"][0]["tags"] == ["urgent", "work"]


class TestExtractJsonFailures:
    def test_completely_invalid(self) -> None:
        result = _extract_json("I don't have any JSON for you today.", "test")
        assert result["_parse_error"] is True

    def test_empty_string(self) -> None:
        result = _extract_json("", "test")
        assert result["_parse_error"] is True

    def test_partial_json(self) -> None:
        result = _extract_json('{"incomplete": ', "test")
        assert result["_parse_error"] is True

    def test_non_json_with_braces(self) -> None:
        result = _extract_json("function() { return true; }", "test")
        assert result["_parse_error"] is True
