import hashlib
from pathlib import Path
from typing import Any

import yaml

from src.config import get_settings
from src.orchestrator.types import (
    Context,
    Pipeline,
    PostProcessingJob,
    Step,
    StepResult,
)
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.config")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

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

    steps = []
    for step_raw in raw.get("steps", []):
        steps.append(Step(
            id=step_raw["id"],
            type=step_raw["type"],
            prompt=step_raw.get("prompt"),
            model=step_raw.get("model"),
            tool=step_raw.get("tool"),
            query=step_raw.get("query"),
            operation=step_raw.get("operation"),
            input=step_raw.get("input"),
            output_schema=step_raw.get("output_schema"),
            stream=step_raw.get("stream", False),
            conditions=step_raw.get("conditions"),
            transform=step_raw.get("transform"),
            retry=step_raw.get("retry"),
        ))

    post = None
    if "post_processing" in raw:
        post = [
            PostProcessingJob(job=p["job"], delay=p.get("delay", "0s"))
            for p in raw["post_processing"]
        ]

    pipeline = Pipeline(
        name=raw.get("name", name),
        description=raw.get("description", ""),
        steps=steps,
        post_processing=post,
    )

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

    _config_cache[name] = (raw, _file_mtime(path))
    return raw


def resolve_variable(
    template: str,
    context: Context,
    step_results: dict[str, StepResult],
) -> Any:
    if not isinstance(template, str) or not template.startswith("${"):
        return template

    path = template.strip("${}").strip()

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
