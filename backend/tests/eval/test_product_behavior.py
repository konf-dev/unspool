"""Product behavior evals — tool assertions + LLM-as-judge.

These test whether the agent calls the right tools with the right args
from the user's perspective. Deterministic tool assertions run always;
LLM-as-judge requires --eval flag.

Run with: pytest tests/eval/test_product_behavior.py --eval -v --timeout=120
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.conftest import load_scenarios
from tests.eval.judge import judge_scenario
from tests.eval.runner import EvalResult, run_eval_scenario

SCENARIOS = load_scenarios("product_behavior.json")


def _scenario_ids() -> list[str]:
    return [s["id"] for s in SCENARIOS]


def _check_tool_assertion(result: EvalResult, assertion: dict[str, Any]) -> str | None:
    """Check a single tool assertion. Returns error message or None."""
    tool_name = assertion.get("tool")
    tool_one_of = assertion.get("tool_one_of")
    args_contain = assertion.get("args_contain", {})
    args_present = assertion.get("args_present", [])

    # Resolve which tool to check
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

    # Check args_contain (substring match, case-insensitive)
    for key, substring in args_contain.items():
        if not result.any_tool_arg_contains(matched_tool, key, substring):
            all_args = result.all_tool_args(matched_tool)
            actual_values = [a.get(key, "<missing>") for a in all_args]
            return (
                f"tool '{matched_tool}' arg '{key}' should contain '{substring}', "
                f"got: {actual_values}"
            )

    # Check args_present
    for key in args_present:
        all_args = result.all_tool_args(matched_tool)
        if not any(key in a for a in all_args):
            return f"tool '{matched_tool}' missing required arg '{key}'"

    return None


@pytest.mark.eval
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_ids())
async def test_product_behavior(
    scenario: dict[str, Any],
    eval_config: dict[str, Any],
    results_dir: Path,
) -> None:
    result = await run_eval_scenario(
        conversation=scenario["conversation"],
        tool_results=scenario.get("tool_results"),
    )

    assert result.response, f"empty response for scenario {scenario['id']}"

    # 1. Deterministic tool assertions (free, no LLM)
    tool_assertion_errors: list[str] = []
    for assertion in scenario.get("tool_assertions", []):
        error = _check_tool_assertion(result, assertion)
        if error:
            tool_assertion_errors.append(error)

    # 2. LLM-as-judge on response quality
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
        "tool_calls": [
            {"name": tc["name"], "args": tc["args"]} for tc in result.tool_calls
        ],
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
