"""Proactive condition evaluator registry."""

from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from src.db import queries as db
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

_log = get_logger("proactive.evaluators")

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


def get_evaluator(name: str) -> ConditionEvaluator | None:
    return _CONDITION_EVALUATORS.get(name)


@register_condition("urgent_items")
async def _eval_urgent_items(
    params: dict[str, Any], user_id: str, profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    hours = params.get("hours", 24)
    items = await db.get_proactive_items(user_id, hours=hours)
    if items:
        return {"items": items, "profile": profile or {}}
    return None


@register_condition("days_absent")
async def _eval_days_absent(
    params: dict[str, Any], user_id: str, profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_days = params.get("min_days", 3)
    p = profile or {}
    last_interaction = p.get("last_interaction_at")
    if not last_interaction:
        return None
    try:
        if isinstance(last_interaction, str):
            last_dt = datetime.fromisoformat(last_interaction)
        else:
            last_dt = last_interaction
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days_absent = (datetime.now(timezone.utc) - last_dt).days
        if days_absent >= min_days:
            return {"days_absent": days_absent, "profile": p}
    except (ValueError, TypeError) as e:
        report_error("proactive.days_absent_parse_failed", e, user_id=user_id)
    return None


@register_condition("recent_completions")
async def _eval_recent_completions(
    params: dict[str, Any], user_id: str, profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_completions = params.get("min_completions", 3)
    lookback = params.get("lookback_hours", 24)
    count = await db.get_recently_done_count(user_id, hours=lookback)
    if count >= min_completions:
        return {"completion_count": count, "profile": profile or {}}
    return None


@register_condition("slipped_items")
async def _eval_slipped_items(
    params: dict[str, Any], user_id: str, profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    min_absent = params.get("min_absent_days", 3)
    p = profile or {}
    last_interaction = p.get("last_interaction_at")
    if not last_interaction:
        return None
    try:
        if isinstance(last_interaction, str):
            last_dt = datetime.fromisoformat(last_interaction)
        else:
            last_dt = last_interaction
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days_absent = (datetime.now(timezone.utc) - last_dt).days
        if days_absent >= min_absent:
            items = await db.get_slipped_items(user_id)
            if items:
                return {"items": items, "days_absent": days_absent, "profile": p}
    except (ValueError, TypeError) as e:
        report_error("proactive.slipped_items_parse_failed", e, user_id=user_id)
    return None
