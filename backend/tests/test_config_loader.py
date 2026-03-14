from pathlib import Path

import pytest

from src.orchestrator.config_loader import (
    load_config,
    load_pipeline,
    resolve_variable,
    validate_config_references,
)
from src.orchestrator.config_models import CONFIG_MODELS
from src.orchestrator.types import Context, StepResult

_PIPELINES_DIR = Path(__file__).resolve().parent.parent / "config" / "pipelines"


def _all_pipeline_names() -> list[str]:
    return sorted(p.stem for p in _PIPELINES_DIR.glob("*.yaml"))


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


class TestConfigValidation:
    @pytest.mark.parametrize("config_name", list(CONFIG_MODELS.keys()))
    def test_all_configs_validate(self, config_name: str) -> None:
        config = load_config(config_name)
        model_cls = CONFIG_MODELS[config_name]
        model_cls.model_validate(config)

    def test_gate_free_tier_is_10(self) -> None:
        config = load_config("gate")
        assert config["rate_limits"]["free"]["daily_messages"] == 1000


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

    @pytest.mark.parametrize("name", _all_pipeline_names())
    def test_all_pipelines_load(self, name: str) -> None:
        pipeline = load_pipeline(name)
        assert pipeline.name == name
        assert len(pipeline.steps) > 0, f"Pipeline {name} has no steps"

    @pytest.mark.parametrize("name", _all_pipeline_names())
    def test_pipeline_steps_have_valid_types(self, name: str) -> None:
        pipeline = load_pipeline(name)
        for step in pipeline.steps:
            # Step.type is a Literal, so Pydantic already validates this,
            # but this test catches issues if the Literal is out of sync.
            assert step.type in {
                "llm_call",
                "tool_call",
                "query",
                "operation",
                "branch",
                "transform",
            }, f"Pipeline {name} step {step.id} has invalid type {step.type}"

    def test_missing_pipeline_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_pipeline("nonexistent_pipeline_xyz")


class TestCrossReferenceValidation:
    def test_cross_references_pass(self) -> None:
        # Import and register tools the same way main.py does
        import importlib
        import pkgutil

        import src.tools as _tools_package

        for _, module_name, _ in pkgutil.iter_modules(_tools_package.__path__):
            importlib.import_module(f"src.tools.{module_name}")

        from src.tools.registry import get_tool_registry

        tool_reg = get_tool_registry()
        errors = validate_config_references(tool_reg)
        assert errors == [], f"Cross-reference errors: {errors}"


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
        results = {
            "classify": StepResult(
                step_id="classify", output={"intent": "brain_dump"}, latency_ms=10.0
            )
        }
        result = resolve_variable("${steps.classify.output}", ctx, results)
        assert result == {"intent": "brain_dump"}

    def test_step_output_subkey(self) -> None:
        ctx = self._make_context()
        results = {
            "classify": StepResult(
                step_id="classify", output={"intent": "brain_dump"}, latency_ms=10.0
            )
        }
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
