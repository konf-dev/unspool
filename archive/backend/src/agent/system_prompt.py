from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger

_log = get_logger("agent.system_prompt")


def _get_current_time(tz_name: str | None) -> str:
    """Format current time for the system prompt."""
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (KeyError, ValueError):
        tz = timezone.utc
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %H:%M (%Z)")


def build_system_prompt(
    profile: dict[str, Any] | None,
    context_block: str,
) -> str:
    """Build the complete system prompt from template + dynamic data."""
    p = profile or {}
    current_time = _get_current_time(p.get("timezone"))

    try:
        prompt = render_prompt(
            "agent_system.md",
            {
                "profile": p,
                "context": context_block,
                "current_time": current_time,
            },
        )
    except FileNotFoundError:
        _log.error("agent.system_prompt_not_found")
        raise

    return prompt
