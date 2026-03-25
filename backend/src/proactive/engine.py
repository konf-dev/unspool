"""Proactive message engine — evaluate triggers, render via LLM, save."""

import time
from datetime import datetime, timezone
from typing import Any

from src.core.config_loader import load_config
from src.core.prompt_renderer import render_prompt
from src.core.settings import get_settings
from src.core.database import AsyncSessionLocal
from src.db.queries import get_profile, update_profile, append_message_event, save_llm_usage
from src.integrations.gemini import get_gemini_client
from src.proactive.evaluators import get_evaluator
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe, update_current_observation
from src.telemetry.logger import get_logger

_log = get_logger("proactive.engine")


@observe(name="proactive.check")
async def check_proactive(user_id: str) -> dict[str, Any] | None:
    """Evaluate proactive triggers and generate a message if triggered.

    Returns a message dict or None.
    """
    profile = None
    try:
        profile = await get_profile(user_id)
    except Exception as e:
        report_error("proactive.profile_failed", e, user_id=user_id)
        return None

    # Check 6h cooldown
    if profile and profile.get("last_proactive_at"):
        last_dt = profile["last_proactive_at"]
        if isinstance(last_dt, str):
            last_dt = datetime.fromisoformat(last_dt)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)

        diff = datetime.now(timezone.utc) - last_dt
        if diff.total_seconds() < 6 * 3600:
            _log.info(
                "proactive.cooldown_active",
                user_id=user_id,
                seconds_remaining=6 * 3600 - diff.total_seconds(),
            )
            return None

    # Eager cooldown update — lock out concurrent requests before LLM call
    await update_profile(user_id, last_proactive_at=datetime.now(timezone.utc))

    try:
        proactive_config = load_config("proactive")
    except FileNotFoundError:
        return None

    triggers = proactive_config.get("triggers", {})
    sorted_triggers = sorted(triggers.items(), key=lambda t: t[1].get("priority", 99))

    for trigger_name, trigger_config in sorted_triggers:
        if not trigger_config.get("enabled", True):
            continue

        condition = trigger_config.get("condition")
        params = trigger_config.get("params", {})

        evaluator = get_evaluator(condition or "")
        if not evaluator:
            _log.warning("proactive.unknown_condition", condition=condition, trigger=trigger_name)
            continue

        template_vars = await evaluator(params, user_id, profile)
        if template_vars is None:
            continue

        prompt_file = trigger_config.get("prompt")
        if not prompt_file:
            continue

        try:
            rendered = render_prompt(prompt_file, template_vars)

            from google.genai import types

            settings = get_settings()
            client = get_gemini_client()

            start = time.perf_counter()
            response = await client.aio.models.generate_content(
                model=settings.BACKGROUND_MODEL,
                contents="Generate the proactive message.",
                config=types.GenerateContentConfig(
                    system_instruction=rendered,
                    temperature=0.8,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            latency_ms = round((time.perf_counter() - start) * 1000)
            content = response.text.strip()

            update_current_observation(
                input=[{"role": "system", "content": rendered[:200]}],
                output=content,
            )

            usage_meta = getattr(response, "usage_metadata", None)
            await save_llm_usage(
                pipeline="proactive",
                model=settings.BACKGROUND_MODEL,
                input_tokens=getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
                output_tokens=getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
                latency_ms=latency_ms,
                user_id=user_id,
            )
        except Exception as e:
            report_error("proactive.render_failed", e, user_id=user_id, trigger=trigger_name)
            continue

        try:
            async with AsyncSessionLocal() as session:
                await append_message_event(
                    session, user_id, "assistant", content,
                    metadata={"type": "proactive", "trigger": trigger_name},
                )
                await session.commit()

            _log.info("proactive.sent", trigger=trigger_name, user_id=user_id)
            return {
                "role": "assistant",
                "content": content,
                "metadata": {"type": "proactive", "trigger": trigger_name},
                "created_at": datetime.now(timezone.utc),
            }
        except Exception as e:
            report_error("proactive.save_failed", e, user_id=user_id, trigger=trigger_name)
            continue

    return None
