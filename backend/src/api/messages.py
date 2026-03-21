from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth.supabase_auth import get_current_user
from src.db import supabase as db
from src.llm.registry import get_llm_provider
from src.config_loader import load_config
from src.prompt_renderer import render_prompt
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe, update_current_observation
from src.telemetry.logger import get_logger

_log = get_logger("api.messages")

router = APIRouter()


def _serialize_message(msg: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in msg.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# --- Proactive condition evaluator registry ---

ConditionEvaluator = Callable[
    [dict[str, Any], str, dict[str, Any] | None],
    Coroutine[Any, Any, dict[str, Any] | None],
]

_CONDITION_EVALUATORS: dict[str, ConditionEvaluator] = {}


def register_condition(name: str) -> Callable[[ConditionEvaluator], ConditionEvaluator]:
    def decorator(fn: ConditionEvaluator) -> ConditionEvaluator:
        _CONDITION_EVALUATORS[name] = fn
        return fn

    return decorator


@register_condition("urgent_items")
async def _eval_urgent_items(
    params: dict[str, Any],
    user_id: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    hours = params.get("hours", 24)
    items = await db.get_proactive_items(user_id, hours=hours)
    if items:
        return {"items": items, "profile": profile or {}}
    return None


@register_condition("days_absent")
async def _eval_days_absent(
    params: dict[str, Any],
    user_id: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_days = params.get("min_days", 3)
    last_interaction = await db.get_last_interaction(user_id)
    if not last_interaction:
        return None
    try:
        last_dt = datetime.fromisoformat(last_interaction)
        days_absent = (datetime.now(timezone.utc) - last_dt).days
        if days_absent >= min_days:
            return {"days_absent": days_absent, "profile": profile or {}}
    except (ValueError, TypeError) as e:
        report_error("proactive.days_absent_parse_failed", e, user_id=user_id)
    return None


@register_condition("recent_completions")
async def _eval_recent_completions(
    params: dict[str, Any],
    user_id: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_completions = params.get("min_completions", 3)
    lookback = params.get("lookback_hours", 24)
    count = await db.get_recently_done_count(user_id, hours=lookback)
    if count >= min_completions:
        return {"completion_count": count, "profile": profile or {}}
    return None


@register_condition("slipped_items")
async def _eval_slipped_items(
    params: dict[str, Any],
    user_id: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_absent = params.get("min_absent_days", 3)
    last_interaction = await db.get_last_interaction(user_id)
    if not last_interaction:
        return None
    try:
        last_dt = datetime.fromisoformat(last_interaction)
        days_absent = (datetime.now(timezone.utc) - last_dt).days
        if days_absent >= min_absent:
            items = await db.get_slipped_items(user_id)
            if items:
                return {
                    "items": items,
                    "days_absent": days_absent,
                    "profile": profile or {},
                }
    except (ValueError, TypeError) as e:
        report_error("proactive.slipped_items_parse_failed", e, user_id=user_id)
    return None


# --- End registry ---


async def _evaluate_trigger(
    trigger_name: str,
    trigger_config: dict[str, Any],
    user_id: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    condition = trigger_config.get("condition")
    params = trigger_config.get("params", {})

    evaluator = _CONDITION_EVALUATORS.get(condition or "")
    if not evaluator:
        _log.warning(
            "proactive.unknown_condition", condition=condition, trigger=trigger_name
        )
        return None

    return await evaluator(params, user_id, profile)


@observe("proactive.check")
async def _check_proactive(user_id: str) -> dict[str, Any] | None:
    profile = None
    try:
        profile = await db.get_profile(user_id)
    except Exception as e:
        report_error("proactive.profile_failed", e, user_id=user_id)
        return None

    # Check cooldown (6 hours)
    if profile and profile.get("last_proactive_at"):
        last_dt = profile["last_proactive_at"]
        if isinstance(last_dt, str):
            last_dt = datetime.fromisoformat(last_dt)

        diff = datetime.now(timezone.utc) - last_dt
        if diff.total_seconds() < 6 * 3600:
            _log.info(
                "proactive.cooldown_active",
                user_id=user_id,
                seconds_remaining=6 * 3600 - diff.total_seconds(),
            )
            return None

    try:
        proactive_config = load_config("proactive")
    except FileNotFoundError:
        return None

    triggers = proactive_config.get("triggers", {})
    metadata_type = proactive_config.get("metadata_type", "proactive")

    sorted_triggers = sorted(
        triggers.items(),
        key=lambda t: t[1].get("priority", 99),
    )

    for trigger_name, trigger_config in sorted_triggers:
        if not trigger_config.get("enabled", True):
            continue

        template_vars = await _evaluate_trigger(
            trigger_name, trigger_config, user_id, profile
        )
        if template_vars is None:
            continue

        prompt_file = trigger_config.get("prompt")
        if not prompt_file:
            continue

        try:
            rendered = render_prompt(prompt_file, template_vars)
            llm_messages = [
                {"role": "system", "content": rendered},
                {"role": "user", "content": "Generate the proactive message."},
            ]
            provider = get_llm_provider()
            result = await provider.generate(messages=llm_messages)
            update_current_observation(
                input=llm_messages,
                output=result.content,
                usage={
                    "input": result.input_tokens,
                    "output": result.output_tokens,
                },
            )
            content = result.content.strip()
        except Exception as e:
            report_error(
                "proactive.render_failed", e, user_id=user_id, trigger=trigger_name
            )
            continue

        try:
            # Mark the time before saving the message to ensure cooldown even if save fails partially
            await db.update_profile(
                user_id, last_proactive_at=datetime.now(timezone.utc)
            )

            msg = await db.save_message(
                user_id=user_id,
                role="assistant",
                content=content,
                metadata={"type": metadata_type, "trigger": trigger_name},
            )
            _log.info("proactive.sent", trigger=trigger_name, user_id=user_id)
            return msg
        except Exception as e:
            report_error(
                "proactive.save_failed", e, user_id=user_id, trigger=trigger_name
            )
            continue

    return None


@router.get("/messages")
async def get_messages(
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict[str, Any]:
    is_initial_load = before is None

    proactive_injected = []
    if is_initial_load:
        # 1. Freshly generated proactive triggers (cooldown-managed)
        proactive_msg = await _check_proactive(user_id)
        if proactive_msg:
            proactive_injected.append(_serialize_message(proactive_msg))
            _log.info("messages.proactive_generated", user_id=user_id)

        # 2. Queued proactive messages (reminders, nudges)
        queued = await db.get_unconsumed_proactive_messages(user_id)
        if queued:
            ids = [str(q["id"]) for q in queued]
            # Convert to message format for frontend
            for q in queued:
                proactive_injected.append(
                    {
                        "id": str(q["id"]),
                        "role": "assistant",
                        "content": q["content"],
                        "createdAt": q["created_at"].isoformat(),
                        "metadata": {
                            "type": "proactive",
                            "trigger": q["trigger_type"],
                            "is_queued": True,
                        },
                    }
                )
            await db.mark_proactive_messages_delivered(user_id, ids)
            _log.info(
                "messages.queued_proactive_delivered",
                count=len(queued),
                user_id=user_id,
            )

    messages = await db.get_messages(user_id, limit=limit, before_id=before)
    serialized = [_serialize_message(m) for m in messages]

    # Prepend any injected messages to the results
    # (they should appear as the most recent messages)
    all_messages = proactive_injected + serialized

    return {
        "messages": all_messages,
        "has_more": len(messages) == limit,
    }
