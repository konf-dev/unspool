import json
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any


from src.config import get_settings
from src.llm.registry import get_llm_provider
from src.orchestrator.config_loader import (
    get_config_hash,
    load_config,
    load_pipeline,
    resolve_variable,
)
from src.orchestrator.prompt_renderer import get_prompt_hash, render_prompt
from src.orchestrator.query_executor import execute_operation, execute_query
from src.orchestrator.types import OUTPUT_SCHEMAS, Context, Step, StepResult
from src.orchestrator.variant_selector import select_variant
from src.telemetry.events import (
    log_llm_usage,
    log_message_completed,
    log_step_completed,
    log_step_error,
    log_step_started,
    log_variant_selected,
)
from src.telemetry.langfuse_integration import (
    observe,
    observe_generation,
    update_current_observation,
)
from src.telemetry.logger import get_logger

_log = get_logger("orchestrator.engine")


def _extract_json(content: str, step_id: str) -> Any:
    """Extract JSON from LLM output, handling common formatting issues.

    LLMs frequently:
    1. Wrap JSON in ```json...``` code fences
    2. Add explanatory text before/after the JSON
    3. Return clean JSON (the happy path)

    Returns the parsed dict/list, or {} if all extraction attempts fail.
    """
    raw = content.strip()

    # Try 1: Direct parse (happy path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try 2: Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try 3: Find the first { or [ and parse from there
    for i, ch in enumerate(raw):
        if ch in "{[":
            try:
                return json.loads(raw[i:])
            except json.JSONDecodeError:
                break

    _log.warning(
        "llm.json_parse_failed",
        step_id=step_id,
        content_preview=content[:300],
    )
    return {}


def _truncate(value: Any, max_len: int = 300) -> Any:
    """Truncate a value for safe logging. Handles strings, dicts, lists."""
    if isinstance(value, str):
        return value[:max_len] + "..." if len(value) > max_len else value
    if isinstance(value, dict):
        return {k: _truncate(v, 100) for k, v in list(value.items())[:10]}
    if isinstance(value, list):
        count = len(value)
        preview = value[:3] if count <= 3 else value[:2] + [f"... +{count - 2} more"]
        return preview
    return value


def _resolve_inputs(
    inputs: dict[str, str | None] | None,
    context: Context,
    step_results: dict[str, StepResult],
) -> dict[str, Any]:
    if not inputs:
        return {}
    resolved = {}
    for key, template in inputs.items():
        if template is None:
            resolved[key] = None
        else:
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
    # Use `is not None` so empty lists/dicts are still passed to templates.
    # This lets prompts distinguish "no items" (empty list) from "not loaded" (absent).
    if context.profile is not None:
        variables["profile"] = context.profile
    if context.open_items is not None:
        variables["open_items"] = context.open_items
    if context.recent_messages is not None:
        variables["recent_messages"] = context.recent_messages
    if context.urgent_items is not None:
        variables["urgent_items"] = context.urgent_items
    if context.memories is not None:
        variables["memories"] = context.memories
    if context.entities is not None:
        variables["entities"] = context.entities
    if context.calendar_events is not None:
        variables["calendar_events"] = context.calendar_events
    if context.graph_context is not None:
        variables["graph_context"] = context.graph_context

    for step_id, result in step_results.items():
        variables[f"step_{step_id}"] = result.output

    variables.update(extra_inputs)
    return variables


@observe_generation("llm_step")
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
    rendered_step = render_prompt(step.prompt, variables)

    # Inject system.md as base personality for all pipeline LLM calls
    try:
        system_base = render_prompt("system.md", {"profile": context.profile})
        system_content = f"{system_base}\n\n---\n\n{rendered_step}"
    except FileNotFoundError:
        system_content = rendered_step

    model = model_override or step.model
    provider = get_llm_provider()
    settings = get_settings()

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": context.user_message},
    ]

    # If recent messages exist, build a proper conversation.
    # recent_messages is ordered newest-first (DESC). Take the 10 most recent,
    # then reverse to chronological order for the LLM conversation.
    if context.recent_messages:
        system_msg = {"role": "system", "content": system_content}
        history = []
        for msg in reversed(context.recent_messages[:10]):
            role = msg.get("role")
            content = msg.get("content")
            if role and content:
                history.append({"role": role, "content": content})
        history.append({"role": "user", "content": context.user_message})
        messages = [system_msg] + history

    start = time.perf_counter()

    if step.stream:
        collected = []
        input_tokens = 0
        output_tokens = 0
        ttft: float | None = None

        async for chunk in provider.stream(messages, model=model):
            if chunk.token:
                if ttft is None:
                    ttft = time.perf_counter() - start
                collected.append(chunk.token)
                yield chunk.token, None
            if chunk.done:
                input_tokens = chunk.input_tokens
                output_tokens = chunk.output_tokens

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        content = "".join(collected)

        _log.info(
            "llm.stream_done",
            step_id=step.id,
            latency_ms=latency_ms,
            output_len=len(content),
            output_preview=content[:300],
            trace_id=context.trace_id,
        )

        used_model = model or settings.LLM_MODEL

        await log_llm_usage(
            trace_id=context.trace_id,
            user_id=context.user_id,
            step_id=step.id,
            pipeline=pipeline_name,
            variant=variant,
            model=used_model,
            provider=settings.LLM_PROVIDER,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            ttft_ms=round(ttft * 1000, 2) if ttft else None,
        )

        update_current_observation(
            name=f"llm_step:{step.id}",
            model=used_model,
            input=messages,
            output=content,
            usage={"input": input_tokens, "output": output_tokens},
            metadata={"pipeline": pipeline_name, "step_id": step.id, "stream": True},
        )

        yield (
            None,
            StepResult(
                step_id=step.id,
                output=content,
                latency_ms=latency_ms,
                tokens_used=input_tokens + output_tokens,
            ),
        )
    else:
        result = await provider.generate(messages, model=model)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        used_model = model or settings.LLM_MODEL

        await log_llm_usage(
            trace_id=context.trace_id,
            user_id=context.user_id,
            step_id=step.id,
            pipeline=pipeline_name,
            variant=variant,
            model=used_model,
            provider=settings.LLM_PROVIDER,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
        )

        update_current_observation(
            name=f"llm_step:{step.id}",
            model=used_model,
            input=messages,
            output=result.content,
            usage={"input": result.input_tokens, "output": result.output_tokens},
            metadata={"pipeline": pipeline_name, "step_id": step.id, "stream": False},
        )

        _log.info(
            "llm.generate_done",
            step_id=step.id,
            latency_ms=latency_ms,
            output_len=len(result.content),
            output_preview=result.content[:300],
            trace_id=context.trace_id,
        )

        output: Any = result.content
        if step.output_schema:
            output = _extract_json(result.content, step.id)
            schema_cls = OUTPUT_SCHEMAS.get(step.output_schema)
            if schema_cls and isinstance(output, dict):
                try:
                    validated = schema_cls.model_validate(output)
                    output = validated.model_dump()
                except Exception as exc:
                    _log.warning(
                        "llm.output_validation_failed",
                        step_id=step.id,
                        schema=step.output_schema,
                        error=str(exc),
                        trace_id=context.trace_id,
                    )

        yield (
            None,
            StepResult(
                step_id=step.id,
                output=output,
                latency_ms=latency_ms,
                tokens_used=result.input_tokens + result.output_tokens,
            ),
        )


@observe("tool_step")
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

    _log.debug(
        "tool.call_start",
        step_id=step.id,
        tool=step.tool,
        inputs={k: _truncate(v) for k, v in resolved_inputs.items()},
        trace_id=context.trace_id,
    )

    start = time.perf_counter()
    result = await tool_fn(**resolved_inputs)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    _log.info(
        "tool.call_done",
        step_id=step.id,
        tool=step.tool,
        latency_ms=latency_ms,
        output_preview=_truncate(result),
        trace_id=context.trace_id,
    )

    update_current_observation(
        name=f"tool:{step.tool}",
        input=_truncate(resolved_inputs),
        output=_truncate(result),
        metadata={"tool": step.tool, "step_id": step.id},
    )

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


@observe("execute_pipeline")
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
    llm_calls = 0
    pipeline_start = time.perf_counter()

    config_snapshot: dict[str, str] = {}
    pipeline_hash = get_config_hash(f"pipeline:{pipeline_name}")
    if pipeline_hash:
        config_snapshot[f"pipeline:{pipeline_name}"] = pipeline_hash
    for step in pipeline.steps:
        if step.prompt:
            h = get_prompt_hash(step.prompt)
            if h:
                config_snapshot[f"prompt:{step.prompt}"] = h

    step_index = 0
    steps = pipeline.steps

    while step_index < len(steps):
        step = steps[step_index]
        log_step_started(context.trace_id, step.id, step.type)

        if step.type == "llm_call":
            llm_calls += 1
            try:
                async for token, result in _execute_llm_step(
                    step, context, step_results, pipeline_name, variant, model_override
                ):
                    if token is not None:
                        yield token
                    if result is not None:
                        step_results[step.id] = result
                        log_step_completed(
                            context.trace_id,
                            step.id,
                            result.latency_ms,
                            tokens=result.tokens_used,
                        )
            except Exception as exc:
                log_step_error(
                    trace_id=context.trace_id,
                    step_id=step.id,
                    step_type=step.type,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    pipeline=pipeline_name,
                )
                raise

        elif step.type == "tool_call":
            try:
                result = await _execute_tool_step(
                    step,
                    context,
                    step_results,
                    tool_registry,
                )
                step_results[step.id] = result
                log_step_completed(context.trace_id, step.id, result.latency_ms)
            except Exception as exc:
                log_step_error(
                    trace_id=context.trace_id,
                    step_id=step.id,
                    step_type=step.type,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    pipeline=pipeline_name,
                )
                raise

        elif step.type == "query":
            try:
                start = time.perf_counter()
                try:
                    resolved_inputs = _resolve_inputs(step.input, context, step_results)
                    output = await execute_query(step.query or step.id, resolved_inputs)
                except NotImplementedError:
                    _log.warning("query.not_implemented", query=step.query or step.id)
                    output = []
                latency_ms = round((time.perf_counter() - start) * 1000, 2)
                step_results[step.id] = StepResult(
                    step_id=step.id,
                    output=output,
                    latency_ms=latency_ms,
                )
                log_step_completed(context.trace_id, step.id, latency_ms)
            except Exception as exc:
                log_step_error(
                    trace_id=context.trace_id,
                    step_id=step.id,
                    step_type=step.type,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    pipeline=pipeline_name,
                )
                raise

        elif step.type == "operation":
            try:
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
                    step_id=step.id,
                    output=output,
                    latency_ms=latency_ms,
                )
                log_step_completed(context.trace_id, step.id, latency_ms)
            except Exception as exc:
                log_step_error(
                    trace_id=context.trace_id,
                    step_id=step.id,
                    step_type=step.type,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    pipeline=pipeline_name,
                )
                raise

        elif step.type == "branch":
            start = time.perf_counter()
            target = _evaluate_branch(step, step_results, context)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            step_results[step.id] = StepResult(
                step_id=step.id,
                output=target,
                latency_ms=latency_ms,
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
                step_id=step.id,
                output=None,
                latency_ms=latency_ms,
            )
            log_step_completed(context.trace_id, step.id, latency_ms)

        else:
            _log.warning("step.unknown_type", step_id=step.id, step_type=step.type)

        step_index += 1

    # tokens_used on StepResult is combined (input+output).
    # Granular per-step tracking is in log_llm_usage calls above.
    # For the pipeline summary, report total tokens used across all steps.
    total_tokens = sum(sr.tokens_used for sr in step_results.values())

    total_latency_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

    if pipeline.post_processing:
        context.post_processing_jobs = pipeline.post_processing

    log_message_completed(
        trace_id=context.trace_id,
        total_latency_ms=total_latency_ms,
        total_input_tokens=total_tokens,
        total_output_tokens=0,  # granular breakdown is in per-step llm_usage logs
        llm_calls=llm_calls,
        pipeline=pipeline_name,
        variant=variant,
        config_snapshot=config_snapshot,
    )
