import json

import pytest

from src.agent.tools import execute_tool, get_tool_definitions
from src.agent.types import AgentState


def _make_state(user_id: str = "test-user") -> AgentState:
    return AgentState(user_id=user_id, trace_id="test-trace", user_message="test")


class TestToolDefinitions:
    def test_all_tools_present(self) -> None:
        tools = get_tool_definitions()
        names = {t["function"]["name"] for t in tools}
        expected = {
            "save_items",
            "mark_done",
            "pick_next",
            "search",
            "get_upcoming",
            "get_progress",
            "update_item",
            "remove_item",
            "save_preference",
            "decompose_task",
            "remember",
        }
        assert names == expected

    def test_tools_have_valid_structure(self) -> None:
        tools = get_tool_definitions()
        for tool in tools:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_tool_descriptions_are_substantial(self) -> None:
        tools = get_tool_definitions()
        for tool in tools:
            desc = tool["function"]["description"]
            assert len(desc) > 30, f"{tool['function']['name']} has too short a description"


class TestRememberHandler:
    @pytest.mark.asyncio
    async def test_remember_sets_flag(self) -> None:
        state = _make_state()
        assert state.should_ingest is False

        result = await execute_tool("remember", {}, "test-user", state)

        assert state.should_ingest is True
        assert result.is_error is False
        assert "acknowledged" in result.output

    @pytest.mark.asyncio
    async def test_remember_idempotent(self) -> None:
        state = _make_state()
        await execute_tool("remember", {}, "test-user", state)
        await execute_tool("remember", {}, "test-user", state)
        assert state.should_ingest is True


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self) -> None:
        state = _make_state()
        result = await execute_tool("nonexistent_tool", {}, "test-user", state)
        assert result.is_error is True
        assert "Unknown tool" in result.output


class TestSaveItemsHandler:
    @pytest.mark.asyncio
    async def test_save_items_sets_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        saved_calls: list[dict] = []

        async def mock_save_item(**kwargs):
            saved_calls.append(kwargs)
            return {"id": "item-1", "interpreted_action": kwargs.get("interpreted_action", "")}

        async def mock_save_event(**kwargs):
            return {"id": "event-1"}

        monkeypatch.setattr("src.agent.tools.db.save_item", mock_save_item)
        monkeypatch.setattr("src.agent.tools.db.save_item_event", mock_save_event)

        state = _make_state()
        result = await execute_tool(
            "save_items",
            {
                "items": [
                    {
                        "raw_text": "call dentist",
                        "interpreted_action": "Call the dentist",
                        "deadline_type": "soft",
                        "deadline_at": None,
                        "energy_estimate": "low",
                    }
                ]
            },
            "test-user",
            state,
        )

        assert state.saved_items is True
        assert result.is_error is False
        data = json.loads(result.output)
        assert data["saved"] == 1
        assert len(saved_calls) == 1

    @pytest.mark.asyncio
    async def test_save_items_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _make_state()
        monkeypatch.setattr("src.agent.tools.db.save_item", lambda **kw: {"id": "x"})
        monkeypatch.setattr("src.agent.tools.db.save_item_event", lambda **kw: {"id": "x"})

        result = await execute_tool("save_items", {"items": []}, "test-user", state)

        data = json.loads(result.output)
        assert data["saved"] == 0


class TestMarkDoneHandler:
    @pytest.mark.asyncio
    async def test_mark_done_no_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_fuzzy(user_id, text):
            return None

        monkeypatch.setattr("src.agent.tools.fuzzy_match_item", mock_fuzzy)

        state = _make_state()
        result = await execute_tool("mark_done", {"text": "something"}, "test-user", state)

        assert result.is_error is True
        assert "Could not find" in result.output

    @pytest.mark.asyncio
    async def test_mark_done_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_fuzzy(user_id, text):
            return {"id": "item-1", "interpreted_action": "Do laundry"}

        async def mock_update(item_id, user_id, **kwargs):
            return {"id": item_id, "status": "done"}

        async def mock_event(**kwargs):
            return {"id": "event-1"}

        monkeypatch.setattr("src.agent.tools.fuzzy_match_item", mock_fuzzy)
        monkeypatch.setattr("src.agent.tools.db.update_item", mock_update)
        monkeypatch.setattr("src.agent.tools.db.save_item_event", mock_event)

        state = _make_state()
        result = await execute_tool("mark_done", {"text": "laundry"}, "test-user", state)

        assert result.is_error is False
        data = json.loads(result.output)
        assert data["completed"] == "Do laundry"


class TestPickNextHandler:
    @pytest.mark.asyncio
    async def test_pick_next_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_items(user_id, limit=50):
            return []

        monkeypatch.setattr("src.agent.tools.db.get_open_items", mock_items)

        state = _make_state()
        result = await execute_tool("pick_next", {}, "test-user", state)

        assert "clear" in result.output.lower() or "no open" in result.output.lower()

    @pytest.mark.asyncio
    async def test_pick_next_returns_item(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items = [
            {
                "id": "item-1",
                "interpreted_action": "Call dentist",
                "urgency_score": 0.8,
                "deadline_type": "soft",
                "deadline_at": None,
                "energy_estimate": "low",
                "last_surfaced_at": None,
            }
        ]

        async def mock_items(user_id, limit=50):
            return items

        async def mock_event(**kwargs):
            return {"id": "event-1"}

        monkeypatch.setattr("src.agent.tools.db.get_open_items", mock_items)
        monkeypatch.setattr("src.agent.tools.db.save_item_event", mock_event)

        state = _make_state()
        result = await execute_tool("pick_next", {}, "test-user", state)

        data = json.loads(result.output)
        assert data["item"] == "Call dentist"
