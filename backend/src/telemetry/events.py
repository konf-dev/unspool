from typing import Any

from src.telemetry.logger import get_logger

_log = get_logger("events")


def log_message_received(trace_id: str, user_id: str, message_length: int) -> None:
    _log.info(
        "message.received",
        trace_id=trace_id,
        user_id=user_id,
        message_length=message_length,
    )


def log_step_started(
    trace_id: str, step_id: str, step_type: str, **kwargs: Any,
) -> None:
    _log.info(
        "step.started",
        trace_id=trace_id,
        step_id=step_id,
        step_type=step_type,
        **kwargs,
    )


def log_step_completed(
    trace_id: str, step_id: str, latency_ms: float, **kwargs: Any,
) -> None:
    _log.info(
        "step.completed",
        trace_id=trace_id,
        step_id=step_id,
        latency_ms=latency_ms,
        **kwargs,
    )


def log_step_error(
    trace_id: str,
    step_id: str,
    step_type: str,
    error_type: str,
    error_message: str,
    pipeline: str,
    **kwargs: Any,
) -> None:
    _log.error(
        "step.error",
        trace_id=trace_id,
        step_id=step_id,
        step_type=step_type,
        error_type=error_type,
        error_message=error_message,
        pipeline=pipeline,
        **kwargs,
    )


async def log_llm_usage(
    trace_id: str,
    user_id: str,
    step_id: str,
    pipeline: str,
    variant: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    ttft_ms: float | None = None,
    config_hash: str | None = None,
) -> None:
    _log.info(
        "llm.usage",
        trace_id=trace_id,
        user_id=user_id,
        step_id=step_id,
        pipeline=pipeline,
        variant=variant,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        ttft_ms=ttft_ms,
        config_hash=config_hash,
    )
    try:
        from src.db.supabase import save_llm_usage
        await save_llm_usage(
            trace_id=trace_id,
            user_id=user_id,
            step_id=step_id,
            pipeline=pipeline,
            variant=variant or "default",
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int(latency_ms),
            ttft_ms=round(ttft_ms) if ttft_ms is not None else None,
            config_hash=config_hash,
        )
    except Exception:
        _log.warning("llm.usage_persist_failed", trace_id=trace_id, exc_info=True)


def log_intent_classified(
    trace_id: str, intent: str, method: str, confidence: float
) -> None:
    _log.info(
        "intent.classified",
        trace_id=trace_id,
        intent=intent,
        method=method,
        confidence=confidence,
    )


def log_variant_selected(trace_id: str, experiment: str, variant: str) -> None:
    _log.info(
        "variant.selected",
        trace_id=trace_id,
        experiment=experiment,
        variant=variant,
    )


def log_message_completed(
    trace_id: str,
    total_latency_ms: float,
    total_input_tokens: int,
    total_output_tokens: int,
    llm_calls: int,
    pipeline: str,
    variant: str,
    config_snapshot: dict[str, str] | None = None,
) -> None:
    combined_hash: str | None = None
    if config_snapshot:
        import hashlib
        joined = "|".join(f"{k}={v}" for k, v in sorted(config_snapshot.items()))
        combined_hash = hashlib.sha256(joined.encode()).hexdigest()[:12]

    _log.info(
        "message.completed",
        trace_id=trace_id,
        total_latency_ms=total_latency_ms,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        llm_calls=llm_calls,
        pipeline=pipeline,
        variant=variant,
        config_hash=combined_hash,
    )
