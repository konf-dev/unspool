import pytest

from src.orchestrator.config_loader import load_config


@pytest.fixture
def intents_config() -> dict:
    return load_config("intents")


class TestIntentsConfig:
    def test_all_intents_present(self, intents_config: dict) -> None:
        expected = {
            "brain_dump",
            "query_next",
            "query_search",
            "query_upcoming",
            "status_done",
            "status_cant",
            "emotional",
            "onboarding",
            "meta",
            "conversation",
        }
        actual = set(intents_config.get("intents", {}).keys())
        assert actual == expected

    def test_each_intent_has_pipeline(self, intents_config: dict) -> None:
        for name, intent_def in intents_config.get("intents", {}).items():
            assert "pipeline" in intent_def, f"Intent {name} missing pipeline"
            assert isinstance(intent_def["pipeline"], str)

    def test_each_intent_has_description(self, intents_config: dict) -> None:
        for name, intent_def in intents_config.get("intents", {}).items():
            assert "description" in intent_def, f"Intent {name} missing description"

    def test_no_fast_patterns(self, intents_config: dict) -> None:
        """All classification goes through LLM — no hardcoded patterns."""
        for name, intent_def in intents_config.get("intents", {}).items():
            assert "fast_patterns" not in intent_def, (
                f"Intent {name} still has fast_patterns — remove them"
            )

    def test_fallback_intent_exists(self, intents_config: dict) -> None:
        fallback = intents_config.get("fallback_intent")
        assert fallback is not None
        assert fallback in intents_config.get("intents", {})

    def test_pipeline_names_match_intent_names(self, intents_config: dict) -> None:
        """By convention, pipeline name matches intent name."""
        for name, intent_def in intents_config.get("intents", {}).items():
            assert intent_def["pipeline"] == name, (
                f"Intent {name} pipeline mismatch: {intent_def['pipeline']}"
            )
