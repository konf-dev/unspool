import asyncio
from typing import Any

from src.db import supabase as db
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger
from src.tools.graph_tools import fetch_graph_context

_log = get_logger("agent.context")


@observe("agent.assemble_context")
async def assemble_context(
    user_id: str,
    message: str,
    trace_id: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Assemble context for the agent.

    Returns:
        (context_block, profile, recent_messages)
        - context_block: formatted <context> text for the system prompt
        - profile: user profile dict
        - recent_messages: list of recent message dicts (chronological)
    """
    profile: dict[str, Any] = {}
    recent_messages: list[dict[str, Any]] = []
    graph_context: str | None = None
    calendar_events: list[dict[str, Any]] = []

    async def _load_profile() -> None:
        nonlocal profile
        try:
            profile = await db.get_profile(user_id)
        except Exception as e:
            report_error("context.profile_failed", e, user_id=user_id)

    async def _load_messages() -> None:
        nonlocal recent_messages
        try:
            msgs = await db.get_messages(user_id, limit=20)
            recent_messages = list(reversed(msgs))
        except Exception as e:
            report_error("context.messages_failed", e, user_id=user_id)

    async def _load_graph() -> None:
        nonlocal graph_context
        try:
            graph_context = await fetch_graph_context(user_id, message=message)
        except Exception as e:
            report_error("context.graph_failed", e, user_id=user_id)

    async def _load_calendar() -> None:
        nonlocal calendar_events
        try:
            calendar_events = await db.get_calendar_events_filtered(user_id)
        except Exception as e:
            report_error("context.calendar_failed", e, user_id=user_id)

    await asyncio.gather(
        _load_profile(),
        _load_messages(),
        _load_graph(),
        _load_calendar(),
        return_exceptions=True,
    )

    # Build context block
    sections: list[str] = []

    if graph_context:
        sections.append(graph_context)

    if calendar_events:
        cal_lines = []
        for event in calendar_events[:10]:
            cal_lines.append(
                f"- {event.get('summary', '')} at {event.get('start_at', '')}"
            )
        if cal_lines:
            sections.append("Calendar:\n" + "\n".join(cal_lines))

    context_block = ""
    if sections:
        context_block = "<context>\n" + "\n\n".join(sections) + "\n</context>"

    _log.info(
        "context.assembled",
        trace_id=trace_id,
        has_graph=bool(graph_context),
        has_calendar=bool(calendar_events),
        message_count=len(recent_messages),
    )

    return context_block, profile, recent_messages
