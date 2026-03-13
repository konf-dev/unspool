import json
import re
from typing import Any

from src.llm.registry import get_llm_provider
from src.orchestrator.config_loader import load_config
from src.orchestrator.prompt_renderer import render_prompt
from src.orchestrator.types import Context
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.intent")


def _try_fast_path(message: str, intents_config: dict[str, Any]) -> tuple[str, float] | None:
    message_lower = message.lower().strip()

    for intent_name, intent_def in intents_config.get("intents", {}).items():
        patterns = intent_def.get("fast_patterns", [])
        for pattern in patterns:
            if re.search(re.escape(pattern.lower()), message_lower):
                return intent_name, 0.9

    return None


async def classify_intent(
    message: str,
    context: Context,
) -> tuple[str, str, float]:
    intents_config = load_config("intents")

    fast_result = _try_fast_path(message, intents_config)
    if fast_result:
        intent_name, confidence = fast_result
        pipeline = intents_config["intents"][intent_name].get("pipeline", intent_name)
        _log.info(
            "intent.fast_path",
            intent=intent_name,
            pipeline=pipeline,
            confidence=confidence,
        )
        return intent_name, pipeline, confidence

    provider = get_llm_provider()
    variables: dict[str, Any] = {
        "user_message": message,
        "recent_messages": context.recent_messages or [],
    }
    rendered = render_prompt("classify_intent.md", variables)

    messages = [
        {"role": "system", "content": rendered},
        {"role": "user", "content": message},
    ]

    result = await provider.generate(messages, model=None)

    try:
        parsed = json.loads(result.content)
        intent_name = parsed.get("intent", "conversation")
        confidence = float(parsed.get("confidence", 0.5))
    except (json.JSONDecodeError, ValueError):
        _log.warning("intent.llm_parse_failed", content=result.content[:200])
        intent_name = intents_config.get("fallback_intent", "conversation")
        confidence = 0.3

    intent_def = intents_config.get("intents", {}).get(intent_name)
    if intent_def:
        pipeline = intent_def.get("pipeline", intent_name)
    else:
        fallback = intents_config.get("fallback_intent", "conversation")
        _log.warning("intent.unknown", intent=intent_name, fallback=fallback)
        intent_name = fallback
        pipeline = intents_config.get("intents", {}).get(fallback, {}).get("pipeline", fallback)

    _log.info(
        "intent.llm_classified",
        intent=intent_name,
        pipeline=pipeline,
        confidence=confidence,
    )
    return intent_name, pipeline, confidence
