"""Personality/voice evals — LLM-as-judge.

Tests the AI's tone, brevity, energy matching, and adherence to
Unspool's first-person voice personality rules.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.conftest import load_scenarios
from tests.eval.judge import judge_scenario
from tests.eval.runner import run_eval_scenario
from tests.eval.test_personality_deterministic import assert_no_forbidden_patterns

SCENARIOS = load_scenarios("personality.json")


def _scenario_ids() -> list[str]:
    return [s["id"] for s in SCENARIOS]


@pytest.mark.eval
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_ids())
async def test_personality(
    scenario: dict[str, Any],
    eval_config: dict[str, Any],
    results_dir: Path,
) -> None:
    result = await run_eval_scenario(
        conversation=scenario["conversation"],
        tool_results=scenario.get("tool_results"),
    )

    assert result.response, f"empty response for scenario {scenario['id']}"
    assert_no_forbidden_patterns(result.response)

    judge_result = await judge_scenario(
        conversation=scenario["conversation"],
        response=result.response,
        response_must=scenario.get("response_must", []),
        response_must_not=scenario.get("response_must_not", []),
        model=eval_config["judge_model"],
    )

    report = {
        "scenario_id": scenario["id"],
        "tags": scenario.get("tags", []),
        "response": result.response,
        "tool_calls": result.tool_names,
        "score": judge_result.score,
        "passed": judge_result.passed,
        "failed": judge_result.failed,
        "total": judge_result.total,
        "details": judge_result.results,
        "commit": eval_config["commit_sha"],
    }
    report_path = results_dir / f"{scenario['id']}.json"
    report_path.write_text(json.dumps(report, indent=2))

    # Personality must be >95%
    assert judge_result.score >= 0.95, (
        f"scenario '{scenario['id']}' scored {judge_result.score:.0%}\n"
        f"Response: {result.response}\n"
        f"{judge_result.summary()}"
    )
