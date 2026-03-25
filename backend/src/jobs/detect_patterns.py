"""Daily pattern detection — db_only and LLM-driven analyses."""

import json
import time
from typing import Any

from src.core.config_loader import load_config
from src.core.prompt_renderer import render_prompt
from src.core.settings import get_settings
from src.db.queries import get_active_users, get_profile, update_profile, save_llm_usage
from src.integrations.gemini import get_gemini_client
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

_log = get_logger("jobs.detect_patterns")


async def run_detect_patterns() -> dict:
    try:
        config = load_config("patterns")
    except FileNotFoundError:
        _log.warning("detect_patterns.no_config")
        return {"updated": 0}

    analyses = config.get("analyses", {})
    users = await get_active_users(days=30)
    _log.info("detect_patterns.start", user_count=len(users))

    updated = 0
    llm_calls = 0

    for user in users:
        user_id = user["id"]
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
                result = await _run_llm_analysis(user_id, name, analysis)
                if result:
                    patterns[name] = result
                    llm_calls += 1

        # Merge with existing patterns
        try:
            existing_profile = await get_profile(user_id)
            existing_patterns = (existing_profile or {}).get("patterns") or {}
            if isinstance(existing_patterns, str):
                existing_patterns = json.loads(existing_patterns)
        except Exception as e:
            report_error("detect_patterns.profile_load_failed", e, user_id=user_id)
            existing_patterns = {}

        merged = {**existing_patterns, **patterns}
        await update_profile(user_id, patterns=merged)
        updated += 1

    _log.info("detect_patterns.done", updated=updated, llm_calls=llm_calls)
    return {"updated": updated, "llm_calls": llm_calls}


async def _run_db_analysis(name: str, user_id: str) -> dict | None:
    if name == "completion_stats":
        from sqlalchemy import text
        from src.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT
                    EXTRACT(DOW FROM created_at) as day_of_week,
                    COUNT(*) as count
                FROM event_stream
                WHERE user_id = :uid                  AND event_type = 'StatusUpdated'
                  AND payload->>'new_status' = 'DONE'
                  AND created_at >= NOW() - interval '30 days'
                GROUP BY day_of_week
                ORDER BY day_of_week
            """), {"uid": user_id})
            rows = result.mappings().all()
            return {"by_day_of_week": {int(r["day_of_week"]): int(r["count"]) for r in rows}}
    return None


async def _run_llm_analysis(
    user_id: str, analysis_name: str, analysis: dict,
) -> dict | None:
    prompt_name = analysis.get("prompt")
    if not prompt_name:
        return None

    confidence_threshold = analysis.get("confidence_threshold", 0.5)
    variables: dict[str, Any] = {"lookback_days": analysis.get("lookback_days", 30)}

    # Load user context for the LLM analysis
    try:
        from sqlalchemy import text as sa_text
        from src.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            # Recent messages
            msg_result = await session.execute(sa_text("""
                SELECT payload->>'content' as content, event_type, created_at
                FROM event_stream
                WHERE user_id = CAST(:uid AS uuid)
                  AND event_type IN ('MessageReceived', 'AgentReplied')
                  AND created_at >= NOW() - (:days || ' days')::interval
                ORDER BY created_at DESC
                LIMIT 50
            """), {"uid": user_id, "days": str(analysis.get("lookback_days", 30))})
            messages = [dict(r) for r in msg_result.mappings().all()]
            variables["recent_messages"] = "\n".join(
                f"[{r.get('event_type', '')}] {r.get('content', '')[:200]}" for r in messages
            ) if messages else "No recent messages."

            # Active graph nodes
            node_result = await session.execute(sa_text("""
                SELECT content, node_type FROM graph_nodes
                WHERE user_id = CAST(:uid AS uuid)
                  AND node_type NOT LIKE 'archived_%%'
                  AND node_type NOT LIKE 'system_%%'
                ORDER BY updated_at DESC LIMIT 30
            """), {"uid": user_id})
            nodes = [dict(r) for r in node_result.mappings().all()]
            variables["active_nodes"] = "\n".join(
                f"[{r.get('node_type', '')}] {r.get('content', '')}" for r in nodes
            ) if nodes else "No active nodes."
    except Exception:
        variables["recent_messages"] = "Failed to load."
        variables["active_nodes"] = "Failed to load."

    try:
        from google.genai import types

        rendered = render_prompt(prompt_name, variables)
        settings = get_settings()
        client = get_gemini_client()

        start = time.perf_counter()
        response = await client.aio.models.generate_content(
            model=settings.BACKGROUND_MODEL,
            contents="Analyze and return results as JSON.",
            config=types.GenerateContentConfig(
                system_instruction=rendered,
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )
        latency_ms = round((time.perf_counter() - start) * 1000)
        content = response.text

        usage_meta = getattr(response, "usage_metadata", None)
        await save_llm_usage(
            pipeline="detect_patterns",
            model=settings.BACKGROUND_MODEL,
            input_tokens=getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
            output_tokens=getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
            latency_ms=latency_ms,
            user_id=user_id,
        )

        parsed = json.loads(content)

        if "patterns" in parsed:
            parsed["patterns"] = [
                p for p in parsed["patterns"]
                if p.get("confidence", 0) >= confidence_threshold
            ]

        return parsed
    except Exception as e:
        report_error("detect_patterns.llm_analysis_failed", e, user_id=user_id)
        return None
