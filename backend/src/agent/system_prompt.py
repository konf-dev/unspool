from typing import Any

from src.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger

_log = get_logger("agent.system_prompt")


def build_system_prompt(
    profile: dict[str, Any] | None,
    context_block: str,
) -> str:
    """Build the complete system prompt from template + dynamic data."""
    try:
        prompt = render_prompt(
            "agent_system",
            {
                "profile": profile or {},
                "context": context_block,
            },
        )
    except FileNotFoundError:
        _log.error("agent.system_prompt_not_found")
        raise

    return prompt
