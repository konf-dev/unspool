"""Context assembly for the hot path — fast reads from graph views, no embedding API calls.

V2: 3-4 SQL queries, 0 API calls. ~100ms total.
Semantic graph search moved to query_graph tool only.
"""

import asyncio
from typing import Any

from src.core.database import AsyncSessionLocal
from src.db.queries import (
    get_messages_from_events,
    get_plate_items,
    get_profile,
    get_recently_done_count,
    get_slipped_items,
    get_deadline_calendar,
    get_metric_summary,
)
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("agent.context")


def _extract_recent_mentions(messages: list[dict[str, Any]]) -> str:
    """Extract user mentions from recent messages not yet in graph (cold path delay)."""
    lines = []
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            content = str(msg["content"]).strip()
            if content and len(content) < 200:
                lines.append(f"  - {content}")
    return "\n".join(lines[-3:]) if lines else ""


@observe(name="agent.assemble_context")
async def assemble_context(
    user_id: str,
    message: str,
    trace_id: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Assemble context for the agent.

    V2: No embedding API calls. 3-4 SQL queries against pre-computed views.
    Returns: (context_block, profile, recent_messages)
    """
    profile: dict[str, Any] = {}
    recent_messages: list[dict[str, Any]] = []
    structured_context: str = ""

    async def _load_profile() -> None:
        nonlocal profile
        try:
            p = await get_profile(user_id)
            if p:
                profile = p
        except Exception as e:
            report_error("context.profile_failed", e, user_id=user_id)

    async def _load_messages() -> None:
        nonlocal recent_messages
        try:
            async with AsyncSessionLocal() as session:
                msgs = await get_messages_from_events(session, user_id, limit=20)
                recent_messages = list(reversed(msgs))
        except Exception as e:
            report_error("context.messages_failed", e, user_id=user_id)

    async def _load_structured_items() -> None:
        """Load deterministic structured data from graph views.

        Runs all queries concurrently for speed (~100ms total instead of sequential).
        """
        nonlocal structured_context
        sections = []

        try:
            # Run all view queries concurrently — each opens its own session
            overdue, plate, calendar, metrics, done_count = await asyncio.gather(
                get_slipped_items(user_id),
                get_plate_items(user_id),
                get_deadline_calendar(user_id),
                get_metric_summary(user_id),
                get_recently_done_count(user_id, hours=48),
                return_exceptions=True,
            )

            # Handle any individual query failures gracefully
            if isinstance(overdue, Exception):
                report_error("context.overdue_failed", overdue, user_id=user_id)
                overdue = []
            if isinstance(plate, Exception):
                report_error("context.plate_failed", plate, user_id=user_id)
                plate = []
            if isinstance(calendar, Exception):
                report_error("context.calendar_failed", calendar, user_id=user_id)
                calendar = {"today": [], "tomorrow": [], "this_week": []}
            if isinstance(metrics, Exception):
                report_error("context.metrics_failed", metrics, user_id=user_id)
                metrics = []
            if isinstance(done_count, Exception):
                report_error("context.done_count_failed", done_count, user_id=user_id)
                done_count = 0

            if overdue:
                lines = []
                for item in overdue:
                    deadline_str = str(item["deadline"]) if item.get("deadline") else ""
                    lines.append(f"  - {item['content']} (was due: {deadline_str})")
                sections.append("Overdue:\n" + "\n".join(lines))

            if plate:
                lines = []
                for item in plate:
                    parts = [item["content"]]
                    if item.get("deadline"):
                        parts.append(f"due: {str(item['deadline'])}")
                    lines.append(f"  - {' — '.join(parts)}")
                sections.append(f"Your plate ({len(plate)}):\n" + "\n".join(lines))
            else:
                sections.append("Your plate: Nothing open right now.")

            cal_lines = []
            for period, items in calendar.items():
                if items:
                    for item in items:
                        time_str = str(item.get("deadline", ""))
                        cal_lines.append(f"  {period.title()}: {item['content']} at {time_str}")
            if cal_lines:
                sections.append("Coming up:\n" + "\n".join(cal_lines))

            if metrics:
                lines = []
                for m in metrics:
                    val = m.get('latest_value') or '?'
                    unit = m.get('unit') or ''
                    date = m.get('latest_date') or ''
                    lines.append(f"  - {m['metric_name']}: {val} {unit} ({date})".rstrip())
                sections.append("Tracking:\n" + "\n".join(lines))

            if done_count > 0:
                sections.append(f"Recently done: {done_count} item{'s' if done_count != 1 else ''} in the last 48h.")

        except Exception as e:
            report_error("context.structured_failed", e, user_id=user_id)

        if sections:
            structured_context = "\n\n".join(sections)

    await asyncio.gather(
        _load_profile(),
        _load_messages(),
        _load_structured_items(),
        return_exceptions=True,
    )

    # Build hierarchical context block
    sections: list[str] = []

    # Tier 1: Structured (deterministic, always accurate)
    if structured_context:
        sections.append(structured_context)

    # Tier 2: Temporal (conversation continuity — recent mentions not yet in graph)
    recent_mentions = _extract_recent_mentions(recent_messages[-3:])
    if recent_mentions:
        sections.append("Just mentioned:\n" + recent_mentions)

    context_block = ""
    if sections:
        context_block = "<context>\n" + "\n\n".join(sections) + "\n</context>"

    _log.info(
        "context.assembled",
        trace_id=trace_id,
        has_structured=bool(structured_context),
        message_count=len(recent_messages),
    )

    return context_block, profile, recent_messages
