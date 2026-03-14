import json
from datetime import datetime, timezone

from src.db.supabase import (
    _get_pool,
    get_active_users,
    get_completion_stats,
    get_message_activity,
    get_profile,
    get_user_first_interaction,
    get_user_messages_text,
    update_profile,
)
from src.llm.registry import get_llm_provider
from src.orchestrator.config_loader import load_config
from src.orchestrator.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger

_log = get_logger("jobs.detect_patterns")

# Maps analysis names to their data-gathering functions.
# Using analysis name (not prompt filename) avoids fragile substring matching.
_DATA_GATHERERS: dict[str, str] = {
    "behavioral_patterns": "behavioral",
    "preference_inference": "preferences",
    "memory_consolidation": "memories",
}


async def run_detect_patterns() -> dict:
    try:
        config = load_config("patterns")
    except FileNotFoundError:
        _log.warning("detect_patterns.no_config")
        config = {"analyses": {"completion_stats": {"type": "db_only", "enabled": True}}}

    analyses = config.get("analyses", {})
    users = await get_active_users(days=30)
    _log.info("detect_patterns.start", user_count=len(users))

    updated = 0
    llm_calls = 0

    for user in users:
        user_id = str(user["id"])
        patterns: dict = {}

        for name, analysis in analyses.items():
            if not analysis.get("enabled", True):
                continue
            if analysis.get("run_on"):
                continue

            analysis_type = analysis.get("type", "db_only")

            if analysis_type == "db_only":
                result = await _run_db_analysis(name, user_id)
                if result:
                    patterns[name] = result

            elif analysis_type == "llm_analysis":
                if not await _has_enough_data(user_id, analysis):
                    continue
                result = await _run_llm_analysis(user_id, name, analysis)
                if result:
                    patterns[name] = result
                    llm_calls += 1

        # Pass dict directly — asyncpg handles JSONB serialization.
        # Do NOT json.dumps() — that causes double-encoding.
        await update_profile(user_id, patterns=patterns)
        updated += 1

    _log.info("detect_patterns.done", updated=updated, llm_calls=llm_calls)
    return {"updated": updated, "llm_calls": llm_calls}


async def _run_db_analysis(name: str, user_id: str) -> dict | None:
    if name == "completion_stats":
        return await get_completion_stats(user_id)
    _log.warning("detect_patterns.unknown_db_analysis", name=name)
    return None


async def _has_enough_data(user_id: str, analysis: dict) -> bool:
    min_data_days = analysis.get("min_data_days", 0)
    min_memories = analysis.get("min_memories", 0)

    if min_data_days > 0:
        first = await get_user_first_interaction(user_id)
        if not first:
            return False
        first_dt = datetime.fromisoformat(first)
        days_active = (datetime.now(timezone.utc) - first_dt).days
        if days_active < min_data_days:
            return False

    if min_memories > 0:
        pool = _get_pool()
        row = await pool.fetchrow(
            "SELECT COUNT(*) AS cnt FROM memories WHERE user_id = $1",
            user_id,
        )
        if not row or int(row["cnt"]) < min_memories:
            return False

    return True


async def _run_llm_analysis(
    user_id: str, analysis_name: str, analysis: dict,
) -> dict | None:
    prompt_name = analysis.get("prompt")
    if not prompt_name:
        _log.warning("detect_patterns.no_prompt", analysis=analysis_name)
        return None

    lookback_days = analysis.get("lookback_days", 30)
    confidence_threshold = analysis.get("confidence_threshold", 0.5)

    data_type = _DATA_GATHERERS.get(analysis_name, "default")
    variables = await _gather_data(user_id, data_type, lookback_days)

    try:
        rendered = render_prompt(prompt_name, variables)
        provider = get_llm_provider()
        result = await provider.generate([
            {"role": "system", "content": rendered},
            {"role": "user", "content": "Analyze and return results as JSON."},
        ])

        parsed = json.loads(result.content)

        if "patterns" in parsed:
            parsed["patterns"] = [
                p for p in parsed["patterns"]
                if p.get("confidence", 0) >= confidence_threshold
            ]

        if "confidence" in parsed and parsed["confidence"] < confidence_threshold:
            return None

        return parsed

    except json.JSONDecodeError:
        _log.warning(
            "detect_patterns.llm_parse_failed",
            prompt=prompt_name,
            user_id=user_id,
        )
        return None
    except Exception:
        _log.warning(
            "detect_patterns.llm_analysis_failed",
            prompt=prompt_name,
            user_id=user_id,
            exc_info=True,
        )
        return None


async def _gather_data(
    user_id: str, data_type: str, lookback_days: int,
) -> dict:
    variables: dict = {"lookback_days": lookback_days}

    if data_type == "behavioral":
        variables["completion_data"] = await get_completion_stats(user_id)
        variables["message_activity"] = await get_message_activity(user_id, days=lookback_days)
        try:
            profile = await get_profile(user_id)
            variables["current_patterns"] = profile.get("patterns", {})
        except Exception:
            variables["current_patterns"] = {}

    elif data_type == "preferences":
        variables["messages"] = await get_user_messages_text(
            user_id, days=lookback_days, limit=50,
        )
        try:
            profile = await get_profile(user_id)
            variables["current_profile"] = {
                "tone_preference": profile.get("tone_preference", "casual"),
                "length_preference": profile.get("length_preference", "medium"),
                "pushiness_preference": profile.get("pushiness_preference", "gentle"),
                "uses_emoji": profile.get("uses_emoji", False),
                "primary_language": profile.get("primary_language", "en"),
            }
        except Exception:
            variables["current_profile"] = {}

    elif data_type == "memories":
        pool = _get_pool()
        rows = await pool.fetch(
            "SELECT id, content, confidence, created_at FROM memories "
            "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
            user_id,
        )
        variables["memories"] = [dict(r) for r in rows]

    return variables
