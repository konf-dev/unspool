from src.agent.types import AgentState, StreamEvent, ToolCall, ToolResult


class TestAgentTypes:
    def test_agent_state_defaults(self) -> None:
        state = AgentState(user_id="u", trace_id="t", user_message="hi")
        assert state.should_ingest is False
        assert state.saved_items is False
        assert state.tool_calls_made == []
        assert state.response_text == ""

    def test_stream_event_defaults(self) -> None:
        event = StreamEvent(type="text_delta")
        assert event.content == ""
        assert event.tool_call_id == ""

    def test_tool_call(self) -> None:
        tc = ToolCall(id="tc-1", name="save_items", arguments='{"items": []}')
        assert tc.id == "tc-1"
        assert tc.name == "save_items"

    def test_tool_result_error(self) -> None:
        result = ToolResult(
            tool_call_id="tc-1",
            name="mark_done",
            output="Not found",
            is_error=True,
        )
        assert result.is_error is True

    def test_tool_result_success(self) -> None:
        result = ToolResult(
            tool_call_id="tc-1",
            name="pick_next",
            output='{"item": "call dentist"}',
        )
        assert result.is_error is False
