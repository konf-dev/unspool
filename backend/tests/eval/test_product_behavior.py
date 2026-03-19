"""Product behavior evals — E2E against deployed API.

Two-phase approach:
1. Send all 25 messages to Railway, collect responses + trace IDs
2. Wait for Langfuse ingestion, batch-fetch tool call data
3. Run Ollama judge + deterministic assertions locally

Run with: pytest tests/eval/test_product_behavior.py --eval -v --timeout=600
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.conftest import load_scenarios
from tests.eval.judge import judge_scenario
from tests.eval.runner import (
    EvalResult,
    cleanup_eval_user,
    enrich_from_langfuse,
    post_scores_to_langfuse,
    send_all_scenarios,
)

SCENARIOS = load_scenarios("product_behavior.json")
_LANGFUSE_SETTLE_SECONDS = 45


def _scenario_ids() -> list[str]:
    return [s["id"] for s in SCENARIOS]


def _check_tool_assertion(result: EvalResult, assertion: dict[str, Any]) -> str | None:
    """Check a single tool assertion. Returns error message or None."""
    tool_name = assertion.get("tool")
    tool_one_of = assertion.get("tool_one_of")
    args_contain = assertion.get("args_contain", {})
    args_present = assertion.get("args_present", [])

    matched_tool: str | None = None
    if tool_name:
        if not result.has_tool(tool_name):
            return f"expected tool '{tool_name}' to be called, got: {result.tool_names}"
        matched_tool = tool_name
    elif tool_one_of:
        for candidate in tool_one_of:
            if result.has_tool(candidate):
                matched_tool = candidate
                break
        if not matched_tool:
            return (
                f"expected one of {tool_one_of} to be called, got: {result.tool_names}"
            )

    if not matched_tool:
        return None

    for key, substring in args_contain.items():
        if not result.any_tool_arg_contains(matched_tool, key, substring):
            all_args = result.all_tool_args(matched_tool)
            actual_values = [a.get(key, "<missing>") for a in all_args]
            return (
                f"tool '{matched_tool}' arg '{key}' should contain '{substring}', "
                f"got: {actual_values}"
            )

    for key in args_present:
        all_args = result.all_tool_args(matched_tool)
        if not any(key in a for a in all_args):
            return f"tool '{matched_tool}' missing required arg '{key}'"

    return None


# Session-scoped: runs once, sends all messages, fetches Langfuse, stores results
_RESULTS: dict[str, EvalResult] = {}


@pytest.fixture(scope="session", autouse=True)
async def _run_all_scenarios() -> None:
    """Phase 1: Clean up, send all messages. Phase 2: Wait, fetch Langfuse."""
    global _RESULTS

    await cleanup_eval_user()

    # Phase 1: Send all messages to Railway
    _RESULTS = await send_all_scenarios(SCENARIOS)

    # Phase 2: Wait for Langfuse to fully ingest, then batch-fetch
    await asyncio.sleep(_LANGFUSE_SETTLE_SECONDS)
    await enrich_from_langfuse(_RESULTS)


@pytest.mark.eval
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_ids())
async def test_product_behavior(
    scenario: dict[str, Any],
    eval_config: dict[str, Any],
    results_dir: Path,
) -> None:
    result = _RESULTS.get(scenario["id"])
    assert result and result.response, f"no response for scenario {scenario['id']}"

    # 1. Deterministic tool assertions
    tool_assertion_errors: list[str] = []
    for assertion in scenario.get("tool_assertions", []):
        error = _check_tool_assertion(result, assertion)
        if error:
            tool_assertion_errors.append(error)

    # 2. LLM-as-judge on response quality (Ollama)
    judge_result = await judge_scenario(
        conversation=scenario["conversation"],
        response=result.response,
        response_must=scenario.get("response_must", []),
        response_must_not=scenario.get("response_must_not", []),
        model=eval_config["judge_model"],
    )

    # Save result
    report = {
        "scenario_id": scenario["id"],
        "tags": scenario.get("tags", []),
        "response": result.response,
        "trace_id": result.trace_id,
        "langfuse_trace_id": result.langfuse_trace_id,
        "tool_calls": [
            {"name": tc["name"], "args": tc["args"]} for tc in result.tool_calls
        ],
        "tool_names_sse": result.tool_names_sse,
        "tool_assertion_errors": tool_assertion_errors,
        "judge_score": judge_result.score,
        "judge_passed": judge_result.passed,
        "judge_failed": judge_result.failed,
        "judge_total": judge_result.total,
        "judge_details": judge_result.results,
        "commit": eval_config["commit_sha"],
    }
    report_path = results_dir / f"{scenario['id']}.json"
    report_path.write_text(json.dumps(report, indent=2))

    # 3. Post scores to Langfuse
    await post_scores_to_langfuse(
        langfuse_trace_id=result.langfuse_trace_id,
        scenario_id=scenario["id"],
        tool_assertion_passed=not tool_assertion_errors,
        judge_score=judge_result.score,
        judge_details=judge_result.results,
    )

    # Assert tool behavior
    assert not tool_assertion_errors, (
        f"scenario '{scenario['id']}' tool assertion failures:\n"
        + "\n".join(f"  - {e}" for e in tool_assertion_errors)
        + f"\nResponse: {result.response}"
        + f"\nTool calls: {result.tool_names}"
    )

    # Assert response quality
    assert judge_result.score >= 0.9, (
        f"scenario '{scenario['id']}' scored {judge_result.score:.0%}\n"
        f"Response: {result.response}\n"
        f"{judge_result.summary()}"
    )
