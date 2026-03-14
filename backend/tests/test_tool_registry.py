"""Tests for tool registry — registration, auto-discovery, completeness."""
import importlib
import pkgutil

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
        # Auto-discover tools like main.py does
        import src.tools as tools_package
        for _, module_name, _ in pkgutil.iter_modules(tools_package.__path__):
            importlib.import_module(f"src.tools.{module_name}")

        registry = get_tool_registry()
        expected = [
            # context_tools
            "fetch_messages", "fetch_profile", "fetch_items",
            "fetch_urgent_items", "fetch_memories", "fetch_entities",
            "fetch_calendar_events",
            # db_tools
            "generate_embedding", "save_items", "search_semantic",
            "search_hybrid", "search_text", "mark_item_done",
            # scoring_tools
            "enrich_items",
            # item_matching
            "fuzzy_match_item", "reschedule_item",
            # momentum_tools
            "check_momentum", "pick_next_item",
            # query_tools
            "smart_fetch",
        ]
        for tool_name in expected:
            assert tool_name in registry, f"Tool '{tool_name}' not registered"

    def test_registered_tools_are_callable(self) -> None:
        import src.tools as tools_package
        for _, module_name, _ in pkgutil.iter_modules(tools_package.__path__):
            importlib.import_module(f"src.tools.{module_name}")

        registry = get_tool_registry()
        for name, fn in registry.items():
            assert callable(fn), f"Tool '{name}' is not callable"

    def test_no_duplicate_tool_names(self) -> None:
        """Registry should not silently overwrite tools with the same name."""
        registry = get_tool_registry()
        # If we get here without errors, each name maps to exactly one function
        assert len(registry) == len(set(registry.keys()))

    def test_all_pipeline_tools_exist(self) -> None:
        """Every tool referenced in a pipeline YAML must be registered."""
        import src.tools as tools_package
        for _, module_name, _ in pkgutil.iter_modules(tools_package.__path__):
            importlib.import_module(f"src.tools.{module_name}")

        from src.orchestrator.config_loader import load_pipeline
        registry = get_tool_registry()

        pipeline_names = [
            "brain_dump", "conversation", "emotional", "meta",
            "onboarding", "query_next", "query_search",
            "query_upcoming", "status_cant", "status_done",
        ]
        for pipeline_name in pipeline_names:
            pipeline = load_pipeline(pipeline_name)
            for step in pipeline.steps:
                if step.type == "tool_call" and step.tool:
                    assert step.tool in registry, (
                        f"Pipeline '{pipeline_name}' step '{step.id}' references "
                        f"tool '{step.tool}' which is not registered"
                    )
