import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.config import get_settings
from src.orchestrator.config_models import CONFIG_MODELS
from src.orchestrator.types import (
    Context,
    Pipeline,
    StepResult,
)
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.config")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_pipeline_cache: dict[str, tuple[Pipeline, float]] = {}
_config_cache: dict[str, tuple[dict[str, Any], float]] = {}
_config_hashes: dict[str, str] = {}


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def load_pipeline(name: str) -> Pipeline:
    path = _CONFIG_DIR / "pipelines" / f"{name}.yaml"
    settings = get_settings()
    is_dev = settings.ENVIRONMENT == "development"

    if name in _pipeline_cache:
        cached, cached_mtime = _pipeline_cache[name]
        if not is_dev or _file_mtime(path) <= cached_mtime:
            return cached

    if not path.exists():
        raise FileNotFoundError(f"Pipeline config not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw_bytes = path.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
    _config_hashes[f"pipeline:{name}"] = file_hash

    pipeline = Pipeline.model_validate(raw)

    _pipeline_cache[name] = (pipeline, _file_mtime(path))
    return pipeline


def load_config(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / f"{name}.yaml"
    settings = get_settings()
    is_dev = settings.ENVIRONMENT == "development"

    if name in _config_cache:
        cached, cached_mtime = _config_cache[name]
        if not is_dev or _file_mtime(path) <= cached_mtime:
            return cached

    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw_bytes = path.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
    _config_hashes[f"config:{name}"] = file_hash

    model_cls = CONFIG_MODELS.get(name)
    if model_cls:
        try:
            model_cls.model_validate(raw)
        except ValidationError as exc:
            _log.error("config.validation_failed", config=name, errors=str(exc))
            raise

    _config_cache[name] = (raw, _file_mtime(path))
    return raw


def validate_config_references(
    tool_registry: dict[str, Callable[..., Any]],
) -> list[str]:
    errors: list[str] = []

    # Check intents → pipeline files
    try:
        intents = load_config("intents")
        for intent_name, intent_def in intents.get("intents", {}).items():
            pipeline_name = intent_def.get("pipeline", intent_name)
            pipeline_path = _CONFIG_DIR / "pipelines" / f"{pipeline_name}.yaml"
            if not pipeline_path.exists():
                errors.append(
                    f"Intent '{intent_name}' references pipeline '{pipeline_name}' "
                    f"but {pipeline_path} does not exist"
                )
    except (FileNotFoundError, ValidationError) as exc:
        errors.append(f"Failed to load intents config: {exc}")

    # Check pipeline steps → tools and prompts
    pipelines_dir = _CONFIG_DIR / "pipelines"
    for pipeline_path in sorted(pipelines_dir.glob("*.yaml")):
        pipeline_name = pipeline_path.stem
        try:
            pipeline = load_pipeline(pipeline_name)
            for step in pipeline.steps:
                if step.tool and step.tool not in tool_registry:
                    errors.append(
                        f"Pipeline '{pipeline_name}' step '{step.id}' references "
                        f"tool '{step.tool}' which is not registered"
                    )
                if step.prompt:
                    prompt_path = _PROMPTS_DIR / step.prompt
                    if not prompt_path.exists():
                        errors.append(
                            f"Pipeline '{pipeline_name}' step '{step.id}' references "
                            f"prompt '{step.prompt}' but {prompt_path} does not exist"
                        )
        except (FileNotFoundError, ValidationError) as exc:
            errors.append(f"Failed to load pipeline '{pipeline_name}': {exc}")

    return errors


def resolve_variable(
    template: str,
    context: Context,
    step_results: dict[str, StepResult],
) -> Any:
    if not isinstance(template, str) or not template.startswith("${"):
        return template

    path = template.removeprefix("${").removesuffix("}").strip()

    if path == "user_message":
        return context.user_message

    if path.startswith("context."):
        attr = path.removeprefix("context.")
        return getattr(context, attr, None)

    if path.startswith("steps."):
        parts = path.removeprefix("steps.").split(".", maxsplit=2)
        step_id = parts[0]
        result = step_results.get(step_id)
        if result is None:
            return None
        if len(parts) == 1:
            return result.output
        field = parts[1]
        if field == "output":
            if len(parts) == 3:
                sub_key = parts[2]
                if isinstance(result.output, dict):
                    return result.output.get(sub_key)
                return getattr(result.output, sub_key, None)
            return result.output
        return getattr(result, field, None)

    return template


def get_config_hash(key: str) -> str | None:
    return _config_hashes.get(key)


def get_all_config_hashes() -> dict[str, str]:
    return dict(_config_hashes)
