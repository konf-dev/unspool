import pytest

from tests.eval.client import EvalClient
from tests.eval.types import CaseResult


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--eval", action="store_true", default=False, help="Run eval tests"
    )
    parser.addoption(
        "--eval-target",
        default="local",
        choices=["local", "staging", "production"],
        help="Eval target environment",
    )
    parser.addoption(
        "--eval-baseline", default=None, help="Baseline report JSON for regression"
    )
    parser.addoption("--eval-tag", default=None, help="Filter cases by tag")


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--eval"):
        return
    skip_eval = pytest.mark.skip(reason="eval tests require --eval flag")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip_eval)


@pytest.fixture(scope="session")
def eval_target(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--eval-target")


@pytest.fixture(scope="session")
def eval_tag(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--eval-tag")


@pytest.fixture(scope="session")
def eval_baseline(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--eval-baseline")


@pytest.fixture(scope="session")
def eval_client(eval_target: str) -> EvalClient:
    import os

    if eval_target == "local":
        return EvalClient(target="local")

    base_url = os.environ.get("EVAL_API_URL", "https://api.unspool.life")
    auth_token = os.environ.get("EVAL_AUTH_TOKEN")
    return EvalClient(target=eval_target, base_url=base_url, auth_token=auth_token)


_session_results: list[CaseResult] = []


@pytest.fixture(scope="session")
def eval_results() -> list[CaseResult]:
    return _session_results


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not session.config.getoption("--eval", default=False):
        return
    if not _session_results:
        return

    from tests.eval.report import build_report, save_report

    target = session.config.getoption("--eval-target", default="local")
    baseline = session.config.getoption("--eval-baseline", default=None)

    report = build_report(_session_results, target, baseline_path=baseline)
    json_path, md_path = save_report(report)

    print(f"\n{'=' * 60}")
    print(f"Eval Report: {report.passed}/{report.total} passed")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"{'=' * 60}")
