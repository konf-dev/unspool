from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth.supabase_auth import get_current_user
from src.db import supabase as db
from src.llm.registry import get_llm_provider
from src.config_loader import load_config
from src.prompt_renderer import render_prompt
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
    except (ValueError, TypeError):
        pass
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
    except (ValueError, TypeError):
        pass
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


async def _check_proactive(user_id: str) -> dict[str, Any] | None:
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

    profile = None
    try:
        profile = await db.get_profile(user_id)
    except Exception:
        pass

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
            provider = get_llm_provider()
            result = await provider.generate(
                messages=[
                    {"role": "system", "content": rendered},
                    {"role": "user", "content": "Generate the proactive message."},
                ],
            )
            content = result.content.strip()
        except Exception:
            _log.warning(
                "proactive.render_failed",
                trigger=trigger_name,
                user_id=user_id,
                exc_info=True,
            )
            continue

        try:
            msg = await db.save_message(
                user_id=user_id,
                role="assistant",
                content=content,
                metadata={"type": metadata_type, "trigger": trigger_name},
            )
            _log.info("proactive.sent", trigger=trigger_name, user_id=user_id)
            return msg
        except Exception:
            _log.warning(
                "proactive.save_failed",
                trigger=trigger_name,
                user_id=user_id,
                exc_info=True,
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

    if is_initial_load:
        proactive_msg = await _check_proactive(user_id)
        if proactive_msg:
            _log.info("messages.proactive_sent", user_id=user_id)

    messages = await db.get_messages(user_id, limit=limit, before_id=before)
    serialized = [_serialize_message(m) for m in messages]

    return {
        "messages": serialized,
        "has_more": len(messages) == limit,
    }
