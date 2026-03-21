import json
from typing import Any

from src.agent.types import AgentState, ToolResult
from src.db import supabase as db
from src.db.utils import normalize_datetime
from src.llm.registry import get_embedding_provider
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger
from src.tools.item_matching import fuzzy_match_item
from src.tools.momentum_tools import pick_next_item
from src.tools.scoring_tools import enrich_items

_log = get_logger("agent.tools")


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "save_items",
                "description": (
                    "Extract and store actionable items from the user's message. "
                    "Call when the user mentions tasks, deadlines, things to do, reminders, or commitments. "
                    "Do NOT call for casual chat, venting, questions, or acknowledgments."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "raw_text": {
                                        "type": "string",
                                        "description": "The user's exact words for this item",
                                    },
                                    "interpreted_action": {
                                        "type": "string",
                                        "description": "Clear concise action: what needs to happen",
                                    },
                                    "deadline_type": {
                                        "type": "string",
                                        "enum": ["hard", "soft", "none"],
                                    },
                                    "deadline_at": {
                                        "type": ["string", "null"],
                                        "description": "ISO 8601 datetime or null",
                                    },
                                    "energy_estimate": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high"],
                                    },
                                },
                                "required": [
                                    "raw_text",
                                    "interpreted_action",
                                    "deadline_type",
                                    "deadline_at",
                                    "energy_estimate",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mark_done",
                "description": (
                    "Mark an item as completed. Call when the user says they finished or did something. "
                    "Pass the text of what they completed — fuzzy matching finds the right item. "
                    "If ambiguous between multiple items, ask the user to clarify instead."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "What the user completed, e.g. 'the laundry'",
                        },
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "pick_next",
                "description": (
                    "Get the single best next action for the user. "
                    "Call when the user asks 'what should I do', 'what's next', or similar. "
                    "Returns one item based on urgency and deadlines. Always present as ONE thing, never a list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": (
                    "Search the user's items, memories, and past conversations. "
                    "Call when the user asks about something they mentioned before, "
                    "or when you need to find related context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for",
                        },
                        "status_filter": {
                            "type": ["string", "null"],
                            "enum": ["open", "done", None],
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_upcoming",
                "description": (
                    "Get items and calendar events coming up soon. "
                    "Call when the user asks 'what's coming up', 'what's this week', or needs a schedule overview."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Hours ahead to look. Default 168 (1 week).",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_progress",
                "description": (
                    "Get completion stats — how many things the user has done recently. "
                    "Call when the user feels unproductive or overwhelmed. "
                    "Use the data to counter negative self-talk with facts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Days to look back. Default 14.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_item",
                "description": (
                    "Update an existing item's deadline or description. "
                    "Call when the user provides new info about an existing task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text identifying the item",
                        },
                        "deadline_at": {
                            "type": ["string", "null"],
                            "description": "New deadline ISO 8601, or null",
                        },
                        "deadline_type": {
                            "type": ["string", "null"],
                            "enum": ["hard", "soft", "none", None],
                        },
                        "interpreted_action": {
                            "type": ["string", "null"],
                            "description": "Updated description, or null",
                        },
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_item",
                "description": (
                    "Deprioritize an item. Call when the user says to forget something or it's no longer relevant."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text identifying the item",
                        },
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_preference",
                "description": (
                    "Update a user preference. Only call when the user explicitly asks "
                    "to change how you interact: 'be more direct', 'use emoji', 'speak Swedish'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": [
                                "tone_preference",
                                "length_preference",
                                "pushiness_preference",
                                "uses_emoji",
                                "primary_language",
                            ],
                        },
                        "value": {"type": "string"},
                    },
                    "required": ["field", "value"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "decompose_task",
                "description": (
                    "Break a large task into smaller micro-steps (5-15 min each). "
                    "Call when the user asks to 'break it down' or agrees to decompose a big task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The task to decompose",
                        },
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "interpreted_action": {"type": "string"},
                                    "energy_estimate": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high"],
                                    },
                                },
                                "required": ["interpreted_action", "energy_estimate"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["text", "steps"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": (
                    "Signal that this turn has info worth persisting to long-term memory. "
                    "Call when the user mentions tasks, ideas, deadlines, preferences, emotional context, "
                    "facts about people/places/projects, or anything worth recalling later. "
                    "Do NOT call for greetings, acknowledgments, or empty exchanges."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_event",
                "description": (
                    "Create an event with a specific time — meetings, appointments, reminders, deadlines, recurring events. "
                    "Call when the user mentions something happening at a specific time or on a specific date. "
                    "For recurring events, use rrule (RFC 5545 format). "
                    "Do NOT use this for tasks without a specific time — use save_items for those."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Event title"},
                        "starts_at": {
                            "type": ["string", "null"],
                            "description": "ISO 8601 start time, or null for reminders",
                        },
                        "ends_at": {
                            "type": ["string", "null"],
                            "description": "ISO 8601 end time, or null",
                        },
                        "is_all_day": {
                            "type": "boolean",
                            "description": "True for all-day events",
                        },
                        "rrule": {
                            "type": ["string", "null"],
                            "description": "RFC 5545 recurrence rule, e.g. FREQ=MONTHLY;BYMONTHDAY=1",
                        },
                        "description": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_entry",
                "description": (
                    "Record a data point for tracking over time — expenses, exercise, sleep, medications, fuel, payments, habits. "
                    "Auto-creates a tracker if this is the first entry for this type. "
                    "Call when the user reports a measurable value: 'spent 450 on fuel', 'ran 5km', 'took my meds', 'slept 7 hours'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tracker_name": {
                            "type": "string",
                            "description": "What's being tracked: 'fuel', 'sleep', 'running', 'electricity'",
                        },
                        "value": {
                            "type": "string",
                            "description": "The value to log: '450', '5', 'true', '7'",
                        },
                        "unit": {
                            "type": ["string", "null"],
                            "description": "Unit: 'SEK', 'km', 'hours', 'liters', null for boolean",
                        },
                        "track_type": {
                            "type": "string",
                            "enum": ["numeric", "boolean", "text", "currency"],
                        },
                        "note": {
                            "type": ["string", "null"],
                            "description": "Optional context: 'shell station', 'couldn't sleep'",
                        },
                    },
                    "required": ["tracker_name", "value", "track_type"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_tracker_summary",
                "description": (
                    "Get recent entries and summary for a tracked metric. "
                    "Call when the user asks about patterns: 'how's my sleep been', 'how much have I spent on fuel'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tracker_name": {
                            "type": "string",
                            "description": "Name of the tracker",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "How many entries to retrieve. Default 20.",
                        },
                    },
                    "required": ["tracker_name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_note",
                "description": (
                    "Store freeform information — outlines, lists, references, recipes, flight details, meeting notes. "
                    "Call when the user shares structured info that isn't a task or event. "
                    "'here's my thesis outline', 'my flight is SK123 at 2pm', 'recipe for pasta'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": ["string", "null"],
                            "description": "Optional title",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full note content",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for retrieval: ['thesis', 'chapter-outline']",
                        },
                    },
                    "required": ["content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_action",
                "description": (
                    "Schedule a future action — nudge, check-in, question, or reminder at a specific time. "
                    "Call when the user says 'remind me Tuesday', 'check in next week', 'ask me about meds every morning'. "
                    "For recurring actions, use rrule."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_type": {
                            "type": "string",
                            "enum": [
                                "nudge",
                                "check_in",
                                "surface_item",
                                "ask_question",
                            ],
                            "description": "What kind of action to trigger",
                        },
                        "execute_at": {
                            "type": "string",
                            "description": "ISO 8601 datetime for when to execute",
                        },
                        "payload": {
                            "type": "object",
                            "description": "Data the action needs: {message: '...', item_id: '...'}",
                            "additionalProperties": True,
                        },
                        "rrule": {
                            "type": ["string", "null"],
                            "description": "RFC 5545 recurrence rule for repeating actions",
                        },
                    },
                    "required": ["action_type", "execute_at"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "manage_collection",
                "description": (
                    "Manage grouped lists — grocery list, packing list, reading list, etc. "
                    "Call when the user mentions a list: 'add milk to grocery list', 'what's on my packing list'. "
                    "Actions: create (new list), add (item to list), list (show contents), dissolve (remove list)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "add", "list", "dissolve"],
                        },
                        "name": {
                            "type": "string",
                            "description": "Collection name: 'grocery list', 'packing for Stockholm'",
                        },
                        "item_text": {
                            "type": ["string", "null"],
                            "description": "For 'add' action: what to add to the collection",
                        },
                    },
                    "required": ["action", "name"],
                    "additionalProperties": False,
                },
            },
        },
    ]


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    user_id: str,
    state: AgentState,
) -> ToolResult:
    _log.info("tool.execute", tool=name, user_id=user_id, trace_id=state.trace_id)

    try:
        handler = _HANDLERS.get(name)
        if not handler:
            return ToolResult(
                tool_call_id="",
                name=name,
                output=f"Unknown tool: {name}",
                is_error=True,
            )
        return await handler(arguments, user_id, state)
    except Exception:
        _log.error("tool.failed", tool=name, user_id=user_id, exc_info=True)
        return ToolResult(
            tool_call_id="",
            name=name,
            output="Internal error. Apologize and ask the user to try again.",
            is_error=True,
        )


async def _handle_save_items(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    items = args.get("items", [])
    enriched = await enrich_items(items)

    saved = []
    for item in enriched:
        result = await db.save_item(
            user_id=user_id,
            raw_text=item.get("raw_text", ""),
            interpreted_action=item.get("interpreted_action", ""),
            deadline_type=item.get("deadline_type"),
            deadline_at=item.get("deadline_at"),
            urgency_score=item.get("urgency_score", 0.0),
            energy_estimate=item.get("energy_estimate"),
        )
        await db.save_item_event(
            item_id=str(result["id"]),
            user_id=user_id,
            event_type="created",
        )
        saved.append(result.get("interpreted_action", ""))

    state.saved_items = True
    return ToolResult(
        tool_call_id="",
        name="save_items",
        output=json.dumps({"saved": len(saved), "items": saved}),
    )


async def _handle_mark_done(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    text = args.get("text", "")
    match = await fuzzy_match_item(user_id, text)
    if not match:
        return ToolResult(
            tool_call_id="",
            name="mark_done",
            output=f"Could not find an open item matching '{text}'. Ask the user to clarify.",
            is_error=True,
        )

    item_id = str(match["id"])
    await db.update_item(item_id, user_id, status="done")
    await db.save_item_event(item_id=item_id, user_id=user_id, event_type="done")

    return ToolResult(
        tool_call_id="",
        name="mark_done",
        output=json.dumps(
            {"completed": match.get("interpreted_action", ""), "item_id": item_id}
        ),
    )


async def _handle_pick_next(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    items = await db.get_open_items(user_id)
    if not items:
        return ToolResult(
            tool_call_id="",
            name="pick_next",
            output="No open items. The user's plate is clear.",
        )

    best = await pick_next_item(items, user_id)
    if not best:
        return ToolResult(
            tool_call_id="",
            name="pick_next",
            output="No open items. The user's plate is clear.",
        )

    await db.save_item_event(
        item_id=str(best["id"]),
        user_id=user_id,
        event_type="surfaced",
    )

    return ToolResult(
        tool_call_id="",
        name="pick_next",
        output=json.dumps(
            {
                "item": best.get("interpreted_action", ""),
                "deadline_type": best.get("deadline_type", "none"),
                "deadline_at": str(best.get("deadline_at", "")),
                "energy": best.get("energy_estimate", "medium"),
            }
        ),
    )


async def _handle_search(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    query = args.get("query", "")
    status_filter = args.get("status_filter")

    results: list[dict[str, Any]] = []
    embedding: list[float] = []

    try:
        embedder = get_embedding_provider()
        embedding = await embedder.embed(query)
        items = await db.search_items_hybrid(user_id, embedding, query, limit=5)
        if status_filter:
            items = [i for i in items if i.get("status") == status_filter]
        results.extend(items)
    except Exception as e:
        report_error("search.embedding_failed", e, user_id=user_id)
        items = await db.search_items_text(user_id, query, limit=5)
        results.extend(items)

    memories = (
        await db.search_memories_semantic(user_id, embedding, limit=3)
        if embedding
        else []
    )

    formatted = []
    for r in results[:5]:
        entry: dict[str, str] = {
            "action": r.get("interpreted_action", ""),
            "raw_text": r.get("raw_text", ""),
            "status": r.get("status", ""),
            "created_at": str(r.get("created_at", "")),
        }
        if r.get("deadline_at"):
            entry["deadline"] = str(r["deadline_at"])
        formatted.append(entry)
    for m in memories[:3]:
        formatted.append({"memory": m.get("content", "")})

    if not formatted:
        return ToolResult(
            tool_call_id="",
            name="search",
            output="No items or memories match that query.",
        )

    return ToolResult(
        tool_call_id="",
        name="search",
        output=json.dumps({"results": formatted}),
    )


async def _handle_get_upcoming(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    hours = args.get("hours", 168)
    items = await db.get_urgent_items(user_id, hours=hours)

    # Get events from both the new events table and legacy calendar_events
    events = await db.get_events(user_id, hours_ahead=hours)
    calendar = await db.get_calendar_events_filtered(user_id)

    timeline = []
    for item in items:
        timeline.append(
            {
                "type": "task",
                "action": item.get("interpreted_action", ""),
                "deadline": str(item.get("deadline_at", "")),
                "deadline_type": item.get("deadline_type", ""),
            }
        )
    for event in events:
        timeline.append(
            {
                "type": "event",
                "title": event.get("title", ""),
                "start": str(event.get("starts_at", "")),
                "recurring": bool(event.get("rrule")),
            }
        )
    for event in calendar:
        timeline.append(
            {
                "type": "calendar",
                "summary": event.get("summary", ""),
                "start": str(event.get("start_at", "")),
            }
        )

    if not timeline:
        return ToolResult(
            tool_call_id="",
            name="get_upcoming",
            output="Nothing coming up.",
        )

    return ToolResult(
        tool_call_id="",
        name="get_upcoming",
        output=json.dumps({"upcoming": timeline}),
    )


async def _handle_get_progress(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    days = args.get("days", 14)
    stats = await db.get_completion_stats(user_id)
    recent = await db.get_recently_done_count(user_id, hours=days * 24)

    return ToolResult(
        tool_call_id="",
        name="get_progress",
        output=json.dumps(
            {
                "completed_last_n_days": recent,
                "days": days,
                "total_30d": stats.get("total_completed", 0),
                "avg_daily": stats.get("avg_daily", 0),
            }
        ),
    )


async def _handle_update_item(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    text = args.get("text", "")
    match = await fuzzy_match_item(user_id, text)
    if not match:
        return ToolResult(
            tool_call_id="",
            name="update_item",
            output=f"Could not find an item matching '{text}'.",
            is_error=True,
        )

    updates: dict[str, Any] = {}
    if args.get("deadline_at") is not None:
        updates["deadline_at"] = args["deadline_at"]
    if args.get("deadline_type") is not None:
        updates["deadline_type"] = args["deadline_type"]
    if args.get("interpreted_action") is not None:
        updates["interpreted_action"] = args["interpreted_action"]

    if updates:
        await db.update_item(str(match["id"]), user_id, **updates)

    return ToolResult(
        tool_call_id="",
        name="update_item",
        output=json.dumps(
            {
                "updated": match.get("interpreted_action", ""),
                "changes": list(updates.keys()),
            }
        ),
    )


async def _handle_remove_item(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    text = args.get("text", "")
    match = await fuzzy_match_item(user_id, text)
    if not match:
        return ToolResult(
            tool_call_id="",
            name="remove_item",
            output=f"Could not find an item matching '{text}'.",
            is_error=True,
        )

    await db.update_item(str(match["id"]), user_id, status="deprioritized")
    await db.save_item_event(
        item_id=str(match["id"]),
        user_id=user_id,
        event_type="deprioritized",
    )

    return ToolResult(
        tool_call_id="",
        name="remove_item",
        output=json.dumps({"removed": match.get("interpreted_action", "")}),
    )


async def _handle_save_preference(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    field = args.get("field", "")
    value = args.get("value", "")

    allowed = {
        "tone_preference",
        "length_preference",
        "pushiness_preference",
        "uses_emoji",
        "primary_language",
        "timezone",
    }
    if field not in allowed:
        return ToolResult(
            tool_call_id="",
            name="save_preference",
            output=f"Unknown preference: {field}",
            is_error=True,
        )

    actual_value: str | bool = value
    if field == "uses_emoji":
        actual_value = value.lower() in ("true", "yes", "1")

    await db.update_profile(user_id, **{field: actual_value})

    return ToolResult(
        tool_call_id="",
        name="save_preference",
        output=json.dumps({"updated": field, "value": str(actual_value)}),
    )


async def _handle_decompose_task(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    text = args.get("text", "")
    steps = args.get("steps", [])

    saved_steps = []
    for step in steps:
        result = await db.save_item(
            user_id=user_id,
            raw_text=f"[subtask of: {text}] {step.get('interpreted_action', '')}",
            interpreted_action=step.get("interpreted_action", ""),
            deadline_type="none",
            energy_estimate=step.get("energy_estimate", "low"),
        )
        await db.save_item_event(
            item_id=str(result["id"]),
            user_id=user_id,
            event_type="created",
        )
        saved_steps.append(step.get("interpreted_action", ""))

    state.saved_items = True
    return ToolResult(
        tool_call_id="",
        name="decompose_task",
        output=json.dumps({"decomposed": text, "steps": saved_steps}),
    )


async def _handle_remember(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    state.should_ingest = True
    return ToolResult(
        tool_call_id="",
        name="remember",
        output='{"acknowledged": true}',
    )


async def _handle_save_event(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    title = args.get("title", "")
    result = await db.save_event(
        user_id=user_id,
        title=title,
        starts_at=args.get("starts_at"),
        ends_at=args.get("ends_at"),
        is_all_day=args.get("is_all_day", False),
        rrule=args.get("rrule"),
        description=args.get("description"),
    )
    state.should_ingest = True
    return ToolResult(
        tool_call_id="",
        name="save_event",
        output=json.dumps(
            {
                "saved": title,
                "event_id": str(result["id"]),
                "starts_at": str(result.get("starts_at", "")),
                "recurring": bool(args.get("rrule")),
            }
        ),
    )


async def _handle_log_entry(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    tracker_name = args.get("tracker_name", "")
    value = args.get("value", "")
    unit = args.get("unit")
    track_type = args.get("track_type", "numeric")
    note = args.get("note")

    tracker = await db.get_or_create_tracker(
        user_id=user_id,
        name=tracker_name,
        unit=unit,
        track_type=track_type,
        created_by="ai",
    )

    entry = await db.save_tracker_entry(
        tracker_id=str(tracker["id"]),
        user_id=user_id,
        value=value,
        note=note,
    )

    return ToolResult(
        tool_call_id="",
        name="log_entry",
        output=json.dumps(
            {
                "tracked": tracker_name,
                "value": value,
                "unit": unit or tracker.get("unit", ""),
                "entry_id": str(entry["id"]),
            }
        ),
    )


async def _handle_get_tracker_summary(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    tracker_name = args.get("tracker_name", "")
    limit = args.get("limit", 20)

    entries = await db.get_tracker_entries(user_id, tracker_name, limit=limit)
    if not entries:
        return ToolResult(
            tool_call_id="",
            name="get_tracker_summary",
            output=f"No entries found for '{tracker_name}'.",
        )

    formatted = []
    for e in entries:
        formatted.append(
            {
                "value": e.get("value", ""),
                "unit": e.get("unit", ""),
                "date": str(e.get("recorded_at", "")),
                "note": e.get("note", ""),
            }
        )

    return ToolResult(
        tool_call_id="",
        name="get_tracker_summary",
        output=json.dumps(
            {
                "tracker": tracker_name,
                "entries": formatted,
                "count": len(formatted),
            }
        ),
    )


async def _handle_save_note(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    content = args.get("content", "")
    title = args.get("title")
    tags = args.get("tags", [])

    result = await db.save_note(
        user_id=user_id,
        content=content,
        title=title,
        tags=tags,
    )

    state.should_ingest = True
    return ToolResult(
        tool_call_id="",
        name="save_note",
        output=json.dumps(
            {
                "saved": title or content[:50],
                "note_id": str(result["id"]),
            }
        ),
    )


async def _handle_schedule_action(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    from datetime import datetime, timezone

    action_type = args.get("action_type", "nudge")
    execute_at_str = args.get("execute_at", "")
    payload = args.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    rrule = args.get("rrule")

    # Save to DB (the execute_actions cron job will pick it up)
    result = await db.save_scheduled_action(
        user_id=user_id,
        action_type=action_type,
        execute_at=execute_at_str,
        payload={**payload, "user_id": user_id},
        rrule=rrule,
    )

    # For short delays (< 10 min), also dispatch via QStash for precision
    try:
        user_tz = await db._get_user_tz(user_id)
        parsed_at = normalize_datetime(execute_at_str, user_tz)
        if parsed_at:
            now = datetime.now(timezone.utc)
            delta = (parsed_at - now).total_seconds()
            if 0 < delta < 600:
                from src.integrations.qstash import dispatch_at

                await dispatch_at(
                    "execute-actions",
                    {"action_ids": [str(result["id"])]},
                    deliver_at=parsed_at,
                )
    except Exception as e:
        report_error("schedule_action.qstash_shortcut_failed", e, user_id=user_id)

    return ToolResult(
        tool_call_id="",
        name="schedule_action",
        output=json.dumps(
            {
                "scheduled": action_type,
                "execute_at": str(result.get("execute_at", "")),
                "recurring": bool(rrule),
                "action_id": str(result["id"]),
            }
        ),
    )


async def _handle_manage_collection(
    args: dict[str, Any], user_id: str, state: AgentState
) -> ToolResult:
    action = args.get("action", "list")
    name = args.get("name", "")

    if action == "create":
        result = await db.save_collection(user_id=user_id, name=name)
        return ToolResult(
            tool_call_id="",
            name="manage_collection",
            output=json.dumps({"created": name, "collection_id": str(result["id"])}),
        )

    if action == "add":
        item_text = args.get("item_text", "")
        # Save as an item first, then add to collection
        item = await db.save_item(
            user_id=user_id,
            raw_text=item_text,
            interpreted_action=item_text,
            deadline_type="none",
        )
        collection = await db.get_collection(user_id, name)
        if not collection:
            collection = await db.save_collection(user_id=user_id, name=name)
        await db.add_to_collection(str(collection["id"]), user_id, str(item["id"]))
        state.saved_items = True
        return ToolResult(
            tool_call_id="",
            name="manage_collection",
            output=json.dumps({"added": item_text, "to": name}),
        )

    if action == "list":
        collection = await db.get_collection(user_id, name)
        if not collection:
            return ToolResult(
                tool_call_id="",
                name="manage_collection",
                output=f"No collection named '{name}' found.",
            )
        item_ids = collection.get("item_ids", [])
        if not item_ids:
            return ToolResult(
                tool_call_id="",
                name="manage_collection",
                output=json.dumps({"collection": name, "items": [], "count": 0}),
            )
        items_data = await db.get_items_filtered(
            user_id=user_id,
            status="open",
            limit=50,
        )
        id_set = set(str(i) for i in item_ids)
        matched = [i for i in items_data if str(i.get("id")) in id_set]
        return ToolResult(
            tool_call_id="",
            name="manage_collection",
            output=json.dumps(
                {
                    "collection": name,
                    "items": [i.get("interpreted_action", "") for i in matched],
                    "count": len(matched),
                }
            ),
        )

    if action == "dissolve":
        collection = await db.get_collection(user_id, name)
        if collection:
            pool = db.get_pool()
            await pool.execute(
                "UPDATE collections SET active = false WHERE id = $1::uuid",
                str(collection["id"]),
            )
        return ToolResult(
            tool_call_id="",
            name="manage_collection",
            output=json.dumps({"dissolved": name}),
        )

    return ToolResult(
        tool_call_id="",
        name="manage_collection",
        output=f"Unknown action: {action}",
        is_error=True,
    )


_HANDLERS: dict[str, Any] = {
    "save_items": _handle_save_items,
    "mark_done": _handle_mark_done,
    "pick_next": _handle_pick_next,
    "search": _handle_search,
    "get_upcoming": _handle_get_upcoming,
    "get_progress": _handle_get_progress,
    "update_item": _handle_update_item,
    "remove_item": _handle_remove_item,
    "save_preference": _handle_save_preference,
    "decompose_task": _handle_decompose_task,
    "remember": _handle_remember,
    "save_event": _handle_save_event,
    "log_entry": _handle_log_entry,
    "get_tracker_summary": _handle_get_tracker_summary,
    "save_note": _handle_save_note,
    "schedule_action": _handle_schedule_action,
    "manage_collection": _handle_manage_collection,
}
