from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound

from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.prompts")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


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
    body = _strip_frontmatter(raw)

    template = _env.from_string(body)
    return template.render(**variables)
