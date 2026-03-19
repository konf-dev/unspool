"""Eval-specific pytest configuration, fixtures, and CLI options."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
RESULTS_DIR = Path(__file__).parent / "results"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--eval",
        action="store_true",
        default=False,
        help="Run LLM-as-judge evals (requires API key)",
    )
    parser.addoption(
        "--eval-target",
        default="local",
        help="Eval target: local, staging, production",
    )
    parser.addoption(
        "--eval-tag",
        default="",
        help="Only run scenarios matching this tag",
    )
    parser.addoption(
        "--eval-model",
        default="",
        help="Override the LLM model for eval runs",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "eval: LLM-as-judge eval (requires --eval)")
    config.addinivalue_line("markers", "deterministic: no LLM calls needed")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_eval = config.getoption("--eval")
    tag_filter = config.getoption("--eval-tag")

    skip_eval = pytest.mark.skip(reason="needs --eval flag to run LLM evals")

    for item in items:
        if item.get_closest_marker("eval") and not run_eval:
            item.add_marker(skip_eval)

        if tag_filter and hasattr(item, "callspec"):
            scenario = item.callspec.params.get("scenario")
            if scenario and tag_filter not in scenario.get("tags", []):
                item.add_marker(pytest.mark.skip(reason=f"tag filter: {tag_filter}"))


@pytest.fixture(scope="session")
def eval_config(request: pytest.FixtureRequest) -> dict[str, Any]:
    model = request.config.getoption("--eval-model") or os.environ.get(
        "LLM_MODEL", "gpt-4.1"
    )
    judge_model = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4.1")
    judge_provider = os.environ.get("EVAL_JUDGE_PROVIDER", "openai")
    return {
        "target": request.config.getoption("--eval-target"),
        "model": model,
        "judge_model": judge_model,
        "judge_provider": judge_provider,
        "commit_sha": os.environ.get("GITHUB_SHA", "local"),
    }


def load_scenarios(filename: str) -> list[dict[str, Any]]:
    path = SCENARIOS_DIR / filename
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def results_dir() -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    return RESULTS_DIR
