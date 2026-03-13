import hashlib
from pathlib import Path
from typing import Any

import yaml as _yaml
from jinja2 import BaseLoader, Environment, TemplateNotFound

from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.prompts")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_prompt_hashes: dict[str, str] = {}
_prompt_meta: dict[str, dict] = {}


class _PromptLoader(BaseLoader):
    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str, Any]:
        path = _PROMPTS_DIR / template
        if not path.exists():
            raise TemplateNotFound(template)
        source = path.read_text(encoding="utf-8")
        return source, str(path), lambda: path.stat().st_mtime


_env = Environment(loader=_PromptLoader(), keep_trailing_newline=True)


def _strip_frontmatter(source: str) -> str:
    if source.startswith("---"):
        parts = source.split("---", maxsplit=2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return source


def render_prompt(prompt_name: str, variables: dict[str, Any]) -> str:
    path = _PROMPTS_DIR / prompt_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    raw = path.read_text(encoding="utf-8")
    _prompt_hashes[prompt_name] = hashlib.sha256(raw.encode()).hexdigest()[:12]
    if raw.startswith("---"):
        parts = raw.split("---", maxsplit=2)
        if len(parts) >= 3:
            _prompt_meta[prompt_name] = _yaml.safe_load(parts[1]) or {}
    body = _strip_frontmatter(raw)

    template = _env.from_string(body)
    return template.render(**variables)


def get_prompt_hash(name: str) -> str | None:
    return _prompt_hashes.get(name)


def get_prompt_meta(name: str) -> dict:
    return _prompt_meta.get(name, {})
