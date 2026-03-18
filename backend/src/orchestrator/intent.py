import json
from typing import Any

from src.llm.registry import get_llm_provider
from src.telemetry.langfuse_integration import observe, update_current_observation
from src.orchestrator.config_loader import load_config
from src.orchestrator.prompt_renderer import render_prompt
from src.orchestrator.types import Context, IntentClassification
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.intent")


@observe("classify_intent")
async def classify_intent(
    message: str,
    context: Context,
) -> tuple[str, str, float]:
    intents_config = load_config("intents")
    fallback = intents_config.get("fallback_intent", "conversation")
    fallback_pipeline = (
        intents_config.get("intents", {}).get(fallback, {}).get("pipeline", fallback)
    )

    # Very short input (1-2 chars) is almost always a casual acknowledgment
    # like "k", "ok", "hi". Skip LLM classification to avoid pipeline crashes.
    if len(message.strip()) <= 2:
        _log.info("intent.short_input", message=message[:10], intent=fallback)
        return fallback, fallback_pipeline, 0.9

    try:
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

        classification_model = intents_config.get("classification_model")

        try:
            raw_structured = await provider.generate_structured(
                messages, schema=IntentClassification, model=classification_model
            )
            structured = IntentClassification.model_validate(
                raw_structured.model_dump()
            )
            intent_name = structured.intent
            confidence = structured.confidence

            update_current_observation(
                model=classification_model or "default",
                input=messages,
                output=json.dumps({"intent": intent_name, "confidence": confidence}),
            )
        except Exception:
            _log.warning("intent.structured_fallback", exc_info=True)
            result = await provider.generate(messages, model=classification_model)

            update_current_observation(
                model=classification_model or "default",
                input=messages,
                output=result.content,
                usage={"input": result.input_tokens, "output": result.output_tokens},
            )

            try:
                parsed = json.loads(result.content)
                intent_name = parsed.get("intent", "conversation")
                confidence = float(parsed.get("confidence", 0.5))
            except (json.JSONDecodeError, ValueError):
                _log.warning("intent.llm_parse_failed", content=result.content[:200])
                intent_name = fallback
                confidence = 0.3
    except Exception:
        _log.error("intent.llm_call_failed", exc_info=True)
        return fallback, fallback_pipeline, 0.1

    intent_def = intents_config.get("intents", {}).get(intent_name)
    if intent_def:
        pipeline = intent_def.get("pipeline", intent_name)
    else:
        _log.warning("intent.unknown", intent=intent_name, fallback=fallback)
        intent_name = fallback
        pipeline = fallback_pipeline

    _log.info(
        "intent.classified",
        intent=intent_name,
        pipeline=pipeline,
        confidence=confidence,
    )
    return intent_name, pipeline, confidence
