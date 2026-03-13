import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any


from src.config import get_settings
from src.llm.registry import get_llm_provider
from src.orchestrator.config_loader import load_config, load_pipeline, resolve_variable
from src.orchestrator.prompt_renderer import render_prompt
from src.orchestrator.query_executor import execute_operation, execute_query
from src.orchestrator.types import Context, Step, StepResult
from src.orchestrator.variant_selector import select_variant
from src.telemetry.events import (
    log_llm_usage,
    log_message_completed,
    log_step_completed,
    log_step_started,
    log_variant_selected,
)
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.engine")


def _resolve_inputs(
    inputs: dict[str, str] | None,
    context: Context,
    step_results: dict[str, StepResult],
) -> dict[str, Any]:
    if not inputs:
        return {}
    resolved = {}
    for key, template in inputs.items():
        resolved[key] = resolve_variable(template, context, step_results)
    return resolved


def _build_prompt_variables(
    context: Context,
    step_results: dict[str, StepResult],
    extra_inputs: dict[str, Any],
) -> dict[str, Any]:
    variables: dict[str, Any] = {
        "user_message": context.user_message,
        "user_id": context.user_id,
    }
    if context.profile:
        variables["profile"] = context.profile
    if context.open_items:
        variables["open_items"] = context.open_items
    if context.recent_messages:
        variables["recent_messages"] = context.recent_messages
    if context.urgent_items:
        variables["urgent_items"] = context.urgent_items
    if context.memories:
        variables["memories"] = context.memories
    if context.entities:
        variables["entities"] = context.entities
    if context.calendar_events:
        variables["calendar_events"] = context.calendar_events

    for step_id, result in step_results.items():
        variables[f"step_{step_id}"] = result.output

    variables.update(extra_inputs)
    return variables


async def _execute_llm_step(
    step: Step,
    context: Context,
    step_results: dict[str, StepResult],
    pipeline_name: str,
    variant: str,
    model_override: str | None = None,
) -> AsyncIterator[tuple[str | None, StepResult | None]]:
    if not step.prompt:
        raise ValueError(f"Step {step.id} is llm_call but has no prompt template")

    extra_inputs = _resolve_inputs(step.input, context, step_results)
    variables = _build_prompt_variables(context, step_results, extra_inputs)
    rendered = render_prompt(step.prompt, variables)

    model = model_override or step.model
    provider = get_llm_provider()
    settings = get_settings()

    messages = [
        {"role": "system", "content": rendered},
        {"role": "user", "content": context.user_message},
    ]

    # If recent messages exist, build a proper conversation
    if context.recent_messages:
        system_msg = {"role": "system", "content": rendered}
        history = []
        for msg in reversed(context.recent_messages[-10:]):
            history.append({"role": msg["role"], "content": msg["content"]})
        history.append({"role": "user", "content": context.user_message})
        messages = [system_msg] + history

    start = time.perf_counter()

    if step.stream:
        collected = []
        input_tokens = 0
        output_tokens = 0

        async for chunk in provider.stream(messages, model=model):
            if chunk.token:
                collected.append(chunk.token)
                yield chunk.token, None
            if chunk.done:
                input_tokens = chunk.input_tokens
                output_tokens = chunk.output_tokens

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        content = "".join(collected)

        await log_llm_usage(
            trace_id=context.trace_id,
            user_id=context.user_id,
            step_id=step.id,
            pipeline=pipeline_name,
            variant=variant,
            model=model or settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

        yield None, StepResult(
            step_id=step.id,
            output=content,
            latency_ms=latency_ms,
            tokens_used=input_tokens + output_tokens,
        )
    else:
        result = await provider.generate(messages, model=model)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        await log_llm_usage(
            trace_id=context.trace_id,
            user_id=context.user_id,
            step_id=step.id,
            pipeline=pipeline_name,
            variant=variant,
            model=model or settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
        )

        output: Any = result.content
        if step.output_schema:
            try:
                output = json.loads(result.content)
            except json.JSONDecodeError:
                _log.warning(
                    "llm.json_parse_failed",
                    step_id=step.id,
                    content_preview=result.content[:200],
                )

        yield None, StepResult(
            step_id=step.id,
            output=output,
            latency_ms=latency_ms,
            tokens_used=result.input_tokens + result.output_tokens,
        )


async def _execute_tool_step(
    step: Step,
    context: Context,
    step_results: dict[str, StepResult],
    tool_registry: dict[str, Callable[..., Any]],
) -> StepResult:
    if not step.tool:
        raise ValueError(f"Step {step.id} is tool_call but has no tool name")

    tool_fn = tool_registry.get(step.tool)
    if not tool_fn:
        raise ValueError(f"Tool not found: {step.tool}")

    resolved_inputs = _resolve_inputs(step.input, context, step_results)

    start = time.perf_counter()
    result = await tool_fn(**resolved_inputs)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    return StepResult(step_id=step.id, output=result, latency_ms=latency_ms)


def _evaluate_branch(
    step: Step,
    step_results: dict[str, StepResult],
    context: Context,
) -> str | None:
    if not step.conditions:
        return None

    for condition in step.conditions:
        var = condition.get("if")
        equals = condition.get("equals")
        goto = condition.get("goto")

        if var and goto:
            resolved = resolve_variable(var, context, step_results)
            if equals is not None and str(resolved) == str(equals):
                return goto
            if equals is None and resolved:
                return goto

    # Default/fallback
    for condition in step.conditions:
        if "default" in condition:
            return condition["default"]

    return None


async def execute_pipeline(
    pipeline_name: str,
    context: Context,
    tool_registry: dict[str, Callable[..., Any]],
) -> AsyncIterator[str]:
    pipeline = load_pipeline(pipeline_name)

    variant = "default"
    model_override: str | None = None
    try:
        variants_config = load_config("variants")
        if pipeline_name in variants_config:
            variant, overrides = await select_variant(
                context.user_id,
                pipeline_name,
                variants_config[pipeline_name],
            )
            log_variant_selected(context.trace_id, pipeline_name, variant)
            model_override = overrides.get("model")
    except FileNotFoundError:
        pass

    step_results: dict[str, StepResult] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    llm_calls = 0
    pipeline_start = time.perf_counter()

    step_index = 0
    steps = pipeline.steps

    while step_index < len(steps):
        step = steps[step_index]
        log_step_started(context.trace_id, step.id, step.type)

        if step.type == "llm_call":
            llm_calls += 1
            async for token, result in _execute_llm_step(
                step, context, step_results, pipeline_name, variant, model_override
            ):
                if token is not None:
                    yield token
                if result is not None:
                    step_results[step.id] = result
                    log_step_completed(
                        context.trace_id, step.id, result.latency_ms,
                        tokens=result.tokens_used,
                    )

        elif step.type == "tool_call":
            result = await _execute_tool_step(
                step, context, step_results, tool_registry,
            )
            step_results[step.id] = result
            log_step_completed(context.trace_id, step.id, result.latency_ms)

        elif step.type == "query":
            start = time.perf_counter()
            try:
                resolved_inputs = _resolve_inputs(step.input, context, step_results)
                output = await execute_query(step.query or step.id, resolved_inputs)
            except NotImplementedError:
                _log.warning("query.not_implemented", query=step.query or step.id)
                output = []
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            step_results[step.id] = StepResult(
                step_id=step.id, output=output, latency_ms=latency_ms,
            )
            log_step_completed(context.trace_id, step.id, latency_ms)

        elif step.type == "operation":
            start = time.perf_counter()
            try:
                resolved_inputs = _resolve_inputs(step.input, context, step_results)
                op_name = step.operation or step.id
                output = await execute_operation(op_name, resolved_inputs)
            except NotImplementedError:
                _log.warning(
                    "operation.not_implemented",
                    operation=step.operation or step.id,
                )
                output = {}
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            step_results[step.id] = StepResult(
                step_id=step.id, output=output, latency_ms=latency_ms,
            )
            log_step_completed(context.trace_id, step.id, latency_ms)

        elif step.type == "branch":
            start = time.perf_counter()
            target = _evaluate_branch(step, step_results, context)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            step_results[step.id] = StepResult(
                step_id=step.id, output=target, latency_ms=latency_ms,
            )
            log_step_completed(context.trace_id, step.id, latency_ms, target=target)

            if target:
                # Jump to target step by id
                found = False
                for i, s in enumerate(steps):
                    if s.id == target:
                        step_index = i
                        found = True
                        break
                if found:
                    continue
                _log.warning("branch.target_not_found", target=target, step_id=step.id)

        elif step.type == "transform":
            start = time.perf_counter()
            _log.warning("transform.not_implemented", step_id=step.id)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            step_results[step.id] = StepResult(
                step_id=step.id, output=None, latency_ms=latency_ms,
            )
            log_step_completed(context.trace_id, step.id, latency_ms)

        else:
            _log.warning("step.unknown_type", step_id=step.id, step_type=step.type)

        step_index += 1

    # tokens_used is total (input+output); granular tracking via llm_usage logs
    for sr in step_results.values():
        total_input_tokens += sr.tokens_used
        # total_output_tokens already tracked by individual llm steps above

    total_latency_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

    if pipeline.post_processing:
        for job in pipeline.post_processing:
            _log.info(
                "post_processing.scheduled",
                job=job.job,
                delay=job.delay,
                trace_id=context.trace_id,
            )

    log_message_completed(
        trace_id=context.trace_id,
        total_latency_ms=total_latency_ms,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        llm_calls=llm_calls,
        pipeline=pipeline_name,
        variant=variant,
    )
