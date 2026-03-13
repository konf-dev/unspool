import pytest

from src.orchestrator.config_loader import load_config


@pytest.fixture
def scoring_config() -> dict:
    return load_config("scoring")


class TestScoringConfig:
    def test_urgency_weights_sum_to_one(self, scoring_config: dict) -> None:
        weights = scoring_config["urgency_weights"]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Urgency weights sum to {total}, expected 1.0"

    def test_urgency_breakpoints_present(self, scoring_config: dict) -> None:
        bp = scoring_config["urgency_breakpoints"]
        assert "overdue" in bp
        assert "imminent" in bp
        assert "approaching" in bp
        assert "distant" in bp

    def test_decay_config_present(self, scoring_config: dict) -> None:
        decay = scoring_config["decay"]
        assert "soft_decay_factor" in decay
        assert "auto_expire_days" in decay
        assert "auto_expire_threshold" in decay
        assert "hard_ramp" in decay
        assert 0 < decay["soft_decay_factor"] < 1

    def test_energy_levels_have_patterns(self, scoring_config: dict) -> None:
        levels = scoring_config["energy_levels"]
        for level_name in ("low", "medium", "high"):
            assert level_name in levels, f"Missing energy level: {level_name}"
            assert "patterns" in levels[level_name], f"{level_name} missing patterns"
            assert len(levels[level_name]["patterns"]) > 0

    def test_momentum_config(self, scoring_config: dict) -> None:
        m = scoring_config["momentum"]
        assert m["lookback_hours"] > 0
        assert m["on_a_roll_threshold"] > 0

    def test_pick_next_config(self, scoring_config: dict) -> None:
        pn = scoring_config["pick_next"]
        assert "boost_hard_deadline" in pn
        assert "boost_low_energy" in pn

    def test_reschedule_config(self, scoring_config: dict) -> None:
        r = scoring_config["reschedule"]
        assert 0 < r["urgency_decay_factor"] < 1
        delays = r["nudge_delay"]
        assert delays["hard_hours"] < delays["soft_days"] * 24

    def test_notifications_config(self, scoring_config: dict) -> None:
        n = scoring_config["notifications"]
        assert 0 <= n["quiet_hours_start"] < 24
        assert 0 < n["quiet_hours_end"] <= 24
        assert n["deadline_window_hours"] > 0


class TestProactiveConfig:
    def test_loads(self) -> None:
        config = load_config("proactive")
        assert "triggers" in config

    def test_triggers_have_required_fields(self) -> None:
        config = load_config("proactive")
        for name, trigger in config["triggers"].items():
            assert "condition" in trigger, f"Trigger {name} missing condition"
            assert "prompt" in trigger, f"Trigger {name} missing prompt"
            assert "priority" in trigger, f"Trigger {name} missing priority"

    def test_triggers_sorted_by_priority(self) -> None:
        config = load_config("proactive")
        priorities = [t["priority"] for t in config["triggers"].values()]
        assert priorities == sorted(priorities), "Triggers should be in priority order"

    def test_all_prompts_exist(self) -> None:
        from pathlib import Path

        config = load_config("proactive")
        prompts_dir = Path(__file__).parent.parent / "prompts"
        for name, trigger in config["triggers"].items():
            prompt_file = prompts_dir / trigger["prompt"]
            assert prompt_file.exists(), f"Trigger {name} references missing prompt: {trigger['prompt']}"
