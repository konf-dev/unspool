from src.tools.registry import get_tool_registry, register_tool


class TestToolRegistry:
    def test_register_and_retrieve(self) -> None:
        @register_tool("test_tool_xyz")
        async def my_tool(x: int) -> int:
            return x * 2

        registry = get_tool_registry()
        assert "test_tool_xyz" in registry
        assert registry["test_tool_xyz"] is my_tool

    def test_all_expected_tools_registered(self) -> None:
        # Force tool module imports
        import src.tools.db_tools  # noqa: F401
        import src.tools.scoring_tools  # noqa: F401
        import src.tools.context_tools  # noqa: F401
        import src.tools.item_matching  # noqa: F401
        import src.tools.momentum_tools  # noqa: F401

        registry = get_tool_registry()
        expected = [
            "fetch_messages", "fetch_profile", "fetch_items",
            "fetch_urgent_items", "fetch_memories", "fetch_entities",
            "fetch_calendar_events",
            "generate_embedding", "save_items", "search_semantic",
            "search_hybrid", "search_text", "mark_item_done",
            "calculate_urgency", "infer_energy", "enrich_items",
            "fuzzy_match_item", "reschedule_item",
            "check_momentum", "pick_next_item",
        ]
        for tool_name in expected:
            assert tool_name in registry, f"Tool '{tool_name}' not registered"

    def test_registered_tools_are_callable(self) -> None:
        import src.tools.db_tools  # noqa: F401

        registry = get_tool_registry()
        for name, fn in registry.items():
            assert callable(fn), f"Tool '{name}' is not callable"
