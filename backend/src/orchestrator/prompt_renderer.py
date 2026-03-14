import hashlib
from pathlib import Path
from typing import Any

import yaml as _yaml
from jinja2 import BaseLoader, Environment, TemplateNotFound

from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.prompts")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_prompt_hashes: dict[str, str] = {}
_prompt_meta: dict[str, dict[str, Any]] = {}


class _PromptLoader(BaseLoader):
    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str, Any]:
        path = _PROMPTS_DIR / template
        if not path.exists():
            raise TemplateNotFound(template)
        raw = path.read_text(encoding="utf-8")

        # Cache hash on load
        _prompt_hashes[template] = hashlib.sha256(raw.encode()).hexdigest()[:12]

        # Strip frontmatter before returning to Jinja2
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", maxsplit=2)
            if len(parts) >= 3:
                _prompt_meta[template] = _yaml.safe_load(parts[1]) or {}
                body = parts[2].lstrip("\n")

        mtime = path.stat().st_mtime
        return body, str(path), lambda: path.stat().st_mtime == mtime


_env = Environment(loader=_PromptLoader(), keep_trailing_newline=True, auto_reload=True)


def render_prompt(prompt_name: str, variables: dict[str, Any]) -> str:
    path = _PROMPTS_DIR / prompt_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    template = _env.get_template(prompt_name)
    return template.render(**variables)


def get_prompt_hash(name: str) -> str | None:
    if name not in _prompt_hashes:
        path = _PROMPTS_DIR / name
        if path.exists():
            raw = path.read_bytes()
            _prompt_hashes[name] = hashlib.sha256(raw).hexdigest()[:12]
    return _prompt_hashes.get(name)


def get_prompt_meta(name: str) -> dict[str, Any]:
    return _prompt_meta.get(name, {})
