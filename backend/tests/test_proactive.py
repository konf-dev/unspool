"""Tests for proactive messaging system."""

import pytest
from src.proactive.evaluators import get_evaluator, _CONDITION_EVALUATORS


class TestConditionRegistry:
    def test_all_conditions_registered(self):
        """All expected conditions are in the registry."""
        expected = {"urgent_items", "days_absent", "recent_completions", "slipped_items"}
        assert expected.issubset(set(_CONDITION_EVALUATORS.keys()))

    def test_get_evaluator_returns_callable(self):
        """get_evaluator returns a callable for known conditions."""
        evaluator = get_evaluator("urgent_items")
        assert evaluator is not None
        assert callable(evaluator)

    def test_get_evaluator_returns_none_for_unknown(self):
        """get_evaluator returns None for unknown conditions."""
        evaluator = get_evaluator("nonexistent_condition")
        assert evaluator is None


class TestProactiveConfig:
    def test_proactive_triggers_load(self):
        """proactive.yaml triggers are well-formed."""
        from src.core.config_loader import load_config

        config = load_config("proactive")
        triggers = config.get("triggers", {})

        for name, trigger in triggers.items():
            assert "condition" in trigger, f"Trigger {name} missing condition"
            assert "prompt" in trigger, f"Trigger {name} missing prompt"
            assert "priority" in trigger, f"Trigger {name} missing priority"
            # Condition must exist in registry
            assert get_evaluator(trigger["condition"]) is not None, \
                f"Trigger {name} has unknown condition: {trigger['condition']}"


class TestScoringConfig:
    def test_scoring_loads(self):
        """scoring.yaml loads with expected keys."""
        from src.core.config_loader import load_config

        config = load_config("scoring")
        assert "notifications" in config
        assert "quiet_hours_start" in config["notifications"]
        assert "quiet_hours_end" in config["notifications"]
