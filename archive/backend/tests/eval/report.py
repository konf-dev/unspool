"""Aggregate eval results into a summary report."""

import json
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"


def generate_summary() -> dict[str, Any]:
    """Read all individual scenario results and produce an aggregate summary."""
    results_dir = RESULTS_DIR
    if not results_dir.exists():
        return {"error": "no results directory"}

    scenario_results: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            scenario_results.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue

    if not scenario_results:
        return {"error": "no results found"}

    total_criteria = sum(r.get("total", 0) for r in scenario_results)
    total_passed = sum(r.get("passed", 0) for r in scenario_results)
    total_failed = sum(r.get("failed", 0) for r in scenario_results)

    # Group by tag
    tag_scores: dict[str, list[float]] = {}
    for r in scenario_results:
        score = r.get("score", 0)
        for tag in r.get("tags", []):
            tag_scores.setdefault(tag, []).append(score)

    tag_averages = {
        tag: sum(scores) / len(scores) for tag, scores in tag_scores.items()
    }

    failures = [
        {
            "scenario": r["scenario_id"],
            "score": r.get("score", 0),
            "details": [d for d in r.get("details", []) if not d.get("pass")],
        }
        for r in scenario_results
        if r.get("score", 1) < 1.0
    ]

    summary = {
        "scenarios": len(scenario_results),
        "criteria_total": total_criteria,
        "criteria_passed": total_passed,
        "criteria_failed": total_failed,
        "overall_score": total_passed / total_criteria if total_criteria else 0,
        "by_tag": tag_averages,
        "failures": failures,
        "commit": scenario_results[0].get("commit", "unknown")
        if scenario_results
        else "unknown",
    }

    summary_path = results_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def print_summary() -> None:
    summary = generate_summary()
    if "error" in summary:
        print(f"Error: {summary['error']}")
        return

    print(f"\n{'=' * 60}")
    print(f"EVAL SUMMARY — {summary['scenarios']} scenarios")
    print(f"{'=' * 60}")
    print(
        f"Overall: {summary['criteria_passed']}/{summary['criteria_total']} "
        f"({summary['overall_score']:.0%})"
    )
    print("\nBy tag:")
    for tag, avg in sorted(summary["by_tag"].items()):
        status = "PASS" if avg >= 0.9 else "FAIL"
        print(f"  {tag}: {avg:.0%} [{status}]")

    if summary["failures"]:
        print(f"\nFailures ({len(summary['failures'])}):")
        for f in summary["failures"]:
            print(f"  {f['scenario']}: {f['score']:.0%}")
            for d in f["details"]:
                print(
                    f"    [{d.get('type', '?')}] {d.get('criterion', '?')}: {d.get('reason', '?')}"
                )
    print(f"\nCommit: {summary['commit']}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    print_summary()
