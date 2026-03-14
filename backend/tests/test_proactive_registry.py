"""Tests for proactive condition evaluator registry."""

from src.api.messages import _CONDITION_EVALUATORS
from src.orchestrator.config_loader import load_config


class TestProactiveRegistry:
    def test_all_config_conditions_have_evaluators(self) -> None:
        """Every condition type used in proactive.yaml must have a registered evaluator."""
        config = load_config("proactive")
        triggers = config.get("triggers", {})
        for trigger_name, trigger_config in triggers.items():
            condition = trigger_config.get("condition")
            assert condition in _CONDITION_EVALUATORS, (
                f"Trigger '{trigger_name}' uses condition '{condition}' "
                f"but no evaluator is registered for it"
            )

    def test_known_evaluators_registered(self) -> None:
        expected = [
            "urgent_items",
            "days_absent",
            "recent_completions",
            "slipped_items",
        ]
        for name in expected:
            assert name in _CONDITION_EVALUATORS, f"Evaluator '{name}' not registered"

    def test_evaluators_are_async_callable(self) -> None:
        import inspect

        for name, fn in _CONDITION_EVALUATORS.items():
            assert callable(fn), f"Evaluator '{name}' is not callable"
            assert inspect.iscoroutinefunction(fn), f"Evaluator '{name}' is not async"

    def test_evaluator_count_matches_config(self) -> None:
        """No orphaned evaluators — every registered evaluator should be used in config."""
        config = load_config("proactive")
        triggers = config.get("triggers", {})
        used_conditions = {t.get("condition") for t in triggers.values()}
        for name in _CONDITION_EVALUATORS:
            assert name in used_conditions, (
                f"Evaluator '{name}' is registered but not used in proactive.yaml"
            )
