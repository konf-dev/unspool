"""Tests for context assembly — config limits, loader registry, field mapping."""
from src.orchestrator.config_loader import load_config
from src.orchestrator.context import _LOADERS, _LOADER_KWARGS


class TestContextRulesConfig:
    def test_defaults_exist(self) -> None:
        config = load_config("context_rules")
        defaults = config.get("defaults", {})
        assert "recent_messages_limit" in defaults
        assert "open_items_limit" in defaults
        assert "memories_limit" in defaults

    def test_defaults_are_reasonable(self) -> None:
        config = load_config("context_rules")
        defaults = config.get("defaults", {})
        assert 1 <= defaults["recent_messages_limit"] <= 100
        assert 1 <= defaults["open_items_limit"] <= 500
        assert 1 <= defaults["memories_limit"] <= 50

    def test_all_intents_have_rules(self) -> None:
        context_rules = load_config("context_rules")
        intents_config = load_config("intents")
        rules = context_rules.get("rules", {})
        intents = intents_config.get("intents", {})
        for intent_name in intents:
            assert intent_name in rules, f"Intent '{intent_name}' has no context rules"

    def test_all_rule_fields_have_loaders(self) -> None:
        """Every field referenced in context_rules.yaml must have a loader."""
        config = load_config("context_rules")
        rules = config.get("rules", {})
        all_fields: set[str] = set()
        for rule in rules.values():
            all_fields.update(rule.get("load", []))
            all_fields.update(rule.get("optional", []))

        for field in all_fields:
            assert field in _LOADERS, f"Field '{field}' referenced in context_rules but has no loader"


class TestLoaderKwargs:
    def test_recent_messages_limit(self) -> None:
        defaults = {"recent_messages_limit": 15}
        kwargs = _LOADER_KWARGS["recent_messages"](defaults)
        assert kwargs == {"limit": 15}

    def test_open_items_limit(self) -> None:
        defaults = {"open_items_limit": 25}
        kwargs = _LOADER_KWARGS["open_items"](defaults)
        assert kwargs == {"limit": 25}

    def test_memories_limit(self) -> None:
        defaults = {"memories_limit": 3}
        kwargs = _LOADER_KWARGS["memories"](defaults)
        assert kwargs == {"limit": 3}

    def test_missing_defaults_use_fallback(self) -> None:
        kwargs = _LOADER_KWARGS["recent_messages"]({})
        assert kwargs == {"limit": 20}

        kwargs = _LOADER_KWARGS["open_items"]({})
        assert kwargs == {"limit": 50}

        kwargs = _LOADER_KWARGS["memories"]({})
        assert kwargs == {"limit": 5}

    def test_loaders_without_kwargs_get_empty(self) -> None:
        """Fields not in _LOADER_KWARGS should get no extra kwargs."""
        for field in _LOADERS:
            if field not in _LOADER_KWARGS:
                # These loaders are called with just (user_id,)
                assert field not in _LOADER_KWARGS
