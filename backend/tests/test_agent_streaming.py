import json

from src.agent.streaming import format_sse_event


class TestSSEFormatting:
    def test_token_event(self) -> None:
        result = format_sse_event("token", content="hello")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "token", "content": "hello"}

    def test_tool_status_running(self) -> None:
        result = format_sse_event("tool_status", tool="save_items", status="running")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {
            "type": "tool_status",
            "tool": "save_items",
            "status": "running",
        }

    def test_tool_status_done(self) -> None:
        result = format_sse_event("tool_status", tool="pick_next", status="done")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "tool_status", "tool": "pick_next", "status": "done"}

    def test_done_event(self) -> None:
        result = format_sse_event("done")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "done"}

    def test_error_event(self) -> None:
        result = format_sse_event("error", content="something went wrong")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "error", "content": "something went wrong"}

    def test_empty_values_omitted(self) -> None:
        result = format_sse_event("token", content="hi", extra_field="")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert "extra_field" not in parsed

    def test_sse_format_has_data_prefix(self) -> None:
        result = format_sse_event("done")
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
