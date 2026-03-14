"""Tests for patterns.yaml config and detect_patterns job structure."""

import pytest

from src.orchestrator.config_loader import load_config
from src.orchestrator.prompt_renderer import render_prompt


class TestPatternsConfig:
    def test_patterns_yaml_loads(self) -> None:
        config = load_config("patterns")
        assert "analyses" in config

    def test_all_analyses_have_required_fields(self) -> None:
        config = load_config("patterns")
        for name, analysis in config["analyses"].items():
            assert "type" in analysis, f"Analysis '{name}' missing type"
            assert analysis["type"] in ("db_only", "llm_analysis"), (
                f"Analysis '{name}' has unknown type '{analysis['type']}'"
            )
            if analysis["type"] == "llm_analysis":
                assert "prompt" in analysis, f"LLM analysis '{name}' missing prompt"
                assert "confidence_threshold" in analysis, (
                    f"LLM analysis '{name}' missing confidence_threshold"
                )

    def test_llm_analysis_prompts_exist(self) -> None:
        """Every prompt referenced in patterns.yaml must exist in prompts/."""
        config = load_config("patterns")
        for name, analysis in config["analyses"].items():
            if analysis["type"] != "llm_analysis":
                continue
            prompt_name = analysis["prompt"]
            # This will raise FileNotFoundError if prompt doesn't exist
            variables = {
                "completion_data": {},
                "message_activity": [],
                "current_patterns": {},
                "lookback_days": 30,
                "messages": [],
                "current_profile": {},
                "memories": [],
            }
            try:
                result = render_prompt(prompt_name, variables)
                assert len(result) > 0
            except FileNotFoundError:
                pytest.fail(
                    f"Analysis '{name}' references missing prompt '{prompt_name}'"
                )

    def test_confidence_thresholds_in_valid_range(self) -> None:
        config = load_config("patterns")
        for name, analysis in config["analyses"].items():
            threshold = analysis.get("confidence_threshold")
            if threshold is not None:
                assert 0.0 <= threshold <= 1.0, (
                    f"Analysis '{name}' confidence_threshold {threshold} out of range"
                )

    def test_min_data_days_reasonable(self) -> None:
        config = load_config("patterns")
        for name, analysis in config["analyses"].items():
            min_days = analysis.get("min_data_days")
            if min_days is not None:
                assert 0 <= min_days <= 365, (
                    f"Analysis '{name}' min_data_days {min_days} seems unreasonable"
                )

    def test_run_on_values_are_valid(self) -> None:
        """run_on should reference a known job name."""
        valid_run_on = {"process_conversation", "detect_patterns"}
        config = load_config("patterns")
        for name, analysis in config["analyses"].items():
            run_on = analysis.get("run_on")
            if run_on:
                assert run_on in valid_run_on, (
                    f"Analysis '{name}' has unknown run_on value '{run_on}'"
                )

    def test_at_least_one_enabled_analysis(self) -> None:
        config = load_config("patterns")
        enabled = [a for a in config["analyses"].values() if a.get("enabled", True)]
        assert len(enabled) > 0, "No analyses are enabled"


class TestDetectPatternsIntegrity:
    def test_completion_stats_is_db_only(self) -> None:
        """completion_stats should always be db_only — it's the baseline."""
        config = load_config("patterns")
        stats = config["analyses"].get("completion_stats")
        assert stats is not None
        assert stats["type"] == "db_only"

    def test_memory_consolidation_runs_on_process_conversation(self) -> None:
        """Memory consolidation should run post-chat, not daily."""
        config = load_config("patterns")
        mem = config["analyses"].get("memory_consolidation")
        assert mem is not None
        assert mem.get("run_on") == "process_conversation"
