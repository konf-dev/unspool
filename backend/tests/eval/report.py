import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tests.eval.types import (
    CategorySummary,
    CaseResult,
    EvalReport,
    RegressionDiff,
)

_RESULTS_DIR = Path(__file__).parent / "results"


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def build_report(
    results: list[CaseResult],
    target: str,
    baseline_path: str | None = None,
) -> EvalReport:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sha = _git_sha()

    categories: dict[str, CategorySummary] = {}
    for r in results:
        cat = r.case_id.split("_")[0] if "_" in r.case_id else "other"
        if cat not in categories:
            categories[cat] = CategorySummary()
        categories[cat].total += 1
        if r.passed:
            categories[cat].passed += 1
        else:
            categories[cat].failed += 1

    report = EvalReport(
        timestamp=now,
        git_sha=sha,
        target=target,
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        categories=categories,
        results=results,
    )

    if baseline_path:
        report.regression_diff = _compute_regression(report, baseline_path)

    return report


def _compute_regression(report: EvalReport, baseline_path: str) -> RegressionDiff:
    try:
        baseline_data = json.loads(Path(baseline_path).read_text())
        baseline = EvalReport(**baseline_data)
    except Exception:
        return RegressionDiff()

    baseline_map = {r.case_id: r for r in baseline.results}
    current_map = {r.case_id: r for r in report.results}

    diff = RegressionDiff()

    for case_id, result in current_map.items():
        prev = baseline_map.get(case_id)
        if prev is None:
            continue
        if prev.passed and not result.passed:
            diff.new_failures.append(case_id)
        if not prev.passed and result.passed:
            diff.new_passes.append(case_id)
        if prev.latency_ms > 0 and result.latency_ms > prev.latency_ms * 1.2:
            diff.latency_regressions.append(
                f"{case_id}: {prev.latency_ms:.0f}ms -> {result.latency_ms:.0f}ms"
            )

    return diff


def save_report(report: EvalReport) -> tuple[Path, Path]:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = _RESULTS_DIR / f"{report.timestamp}_{report.git_sha}.json"
    md_path = _RESULTS_DIR / f"{report.timestamp}_{report.git_sha}.md"

    json_path.write_text(report.model_dump_json(indent=2))
    md_path.write_text(_render_markdown(report))

    return json_path, md_path


def _render_markdown(report: EvalReport) -> str:
    lines = [
        f"# Eval Report — {report.timestamp}",
        "",
        f"**Git SHA:** {report.git_sha}  ",
        f"**Target:** {report.target}  ",
        f"**Total:** {report.total} | **Passed:** {report.passed} | **Failed:** {report.failed}",
        "",
        "## Categories",
        "",
        "| Category | Total | Passed | Failed |",
        "|----------|-------|--------|--------|",
    ]

    for cat, summary in sorted(report.categories.items()):
        lines.append(
            f"| {cat} | {summary.total} | {summary.passed} | {summary.failed} |"
        )

    failed = [r for r in report.results if not r.passed]
    if failed:
        lines.extend(["", "## Failed Cases", ""])
        for r in failed:
            lines.append(f"### {r.case_id}")
            if r.error:
                lines.append(f"**Error:** {r.error}")
            for ar in r.assertion_results:
                if not ar.passed:
                    lines.append(
                        f"- **{ar.assertion.type}** on `{ar.assertion.field}`: "
                        f"expected `{ar.assertion.value}`, got `{ar.actual}`"
                    )
            for jr in r.judge_results:
                if not jr.passed:
                    lines.append(
                        f"- **Judge ({jr.criterion}):** {jr.score:.1f}/10 — {jr.reasoning}"
                    )
            lines.append("")

    if report.regression_diff:
        diff = report.regression_diff
        if diff.new_failures or diff.new_passes or diff.latency_regressions:
            lines.extend(["## Regression Diff", ""])
            if diff.new_failures:
                lines.append(f"**New failures:** {', '.join(diff.new_failures)}")
            if diff.new_passes:
                lines.append(f"**New passes:** {', '.join(diff.new_passes)}")
            if diff.latency_regressions:
                lines.append("**Latency regressions:**")
                for lr in diff.latency_regressions:
                    lines.append(f"- {lr}")

    lines.append("")
    return "\n".join(lines)
