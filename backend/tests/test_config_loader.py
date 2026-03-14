import pytest

from src.orchestrator.config_loader import load_config, load_pipeline, resolve_variable
from src.orchestrator.types import Context, StepResult


class TestLoadConfig:
    def test_load_intents(self) -> None:
        config = load_config("intents")
        assert "intents" in config
        assert "brain_dump" in config["intents"]
        assert "fallback_intent" in config

    def test_load_gate(self) -> None:
        config = load_config("gate")
        assert "rate_limits" in config

    def test_load_context_rules(self) -> None:
        config = load_config("context_rules")
        assert "rules" in config or "defaults" in config

    def test_missing_config_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent_config_xyz")


class TestLoadPipeline:
    def test_load_brain_dump(self) -> None:
        pipeline = load_pipeline("brain_dump")
        assert pipeline.name == "brain_dump"
        assert len(pipeline.steps) > 0

    def test_load_query_search(self) -> None:
        pipeline = load_pipeline("query_search")
        step_ids = [s.id for s in pipeline.steps]
        assert "analyze" in step_ids
        assert "fetch" in step_ids
        assert "respond" in step_ids

    def test_all_pipelines_load(self) -> None:
        pipeline_names = [
            "brain_dump", "conversation", "emotional", "meta",
            "onboarding", "query_next", "query_search",
            "query_upcoming", "status_cant", "status_done",
        ]
        for name in pipeline_names:
            pipeline = load_pipeline(name)
            assert pipeline.name == name
            assert len(pipeline.steps) > 0, f"Pipeline {name} has no steps"

    def test_missing_pipeline_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_pipeline("nonexistent_pipeline_xyz")


class TestResolveVariable:
    def _make_context(self) -> Context:
        return Context(
            user_id="user-1",
            trace_id="trace-1",
            user_message="hello world",
            profile={"timezone": "US/Eastern"},
            open_items=[{"id": "item-1"}],
        )

    def test_literal_passthrough(self) -> None:
        ctx = self._make_context()
        assert resolve_variable("hello", ctx, {}) == "hello"

    def test_user_message(self) -> None:
        ctx = self._make_context()
        assert resolve_variable("${user_message}", ctx, {}) == "hello world"

    def test_context_attribute(self) -> None:
        ctx = self._make_context()
        result = resolve_variable("${context.user_id}", ctx, {})
        assert result == "user-1"

    def test_context_profile(self) -> None:
        ctx = self._make_context()
        result = resolve_variable("${context.profile}", ctx, {})
        assert result == {"timezone": "US/Eastern"}

    def test_step_output(self) -> None:
        ctx = self._make_context()
        results = {"classify": StepResult(step_id="classify", output={"intent": "brain_dump"}, latency_ms=10.0)}
        result = resolve_variable("${steps.classify.output}", ctx, results)
        assert result == {"intent": "brain_dump"}

    def test_step_output_subkey(self) -> None:
        ctx = self._make_context()
        results = {"classify": StepResult(step_id="classify", output={"intent": "brain_dump"}, latency_ms=10.0)}
        result = resolve_variable("${steps.classify.output.intent}", ctx, results)
        assert result == "brain_dump"

    def test_missing_step_returns_none(self) -> None:
        ctx = self._make_context()
        result = resolve_variable("${steps.missing.output}", ctx, {})
        assert result is None

    def test_missing_context_attr_returns_none(self) -> None:
        ctx = self._make_context()
        result = resolve_variable("${context.nonexistent}", ctx, {})
        assert result is None
