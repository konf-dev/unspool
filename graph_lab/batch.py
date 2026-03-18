"""Batch simulation runner — run many simulations, resume on crash, aggregate results."""

import json
import time
from pathlib import Path

import structlog
from graph_lab.simulate import run_simulation
from graph_lab.src.types import SimulationResult
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()

GRAPH_LAB_ROOT = Path(__file__).parent
RESULTS_DIR = GRAPH_LAB_ROOT / "results"


async def run_batch(
    personas: list[str],
    days: int = 30,
    runs_per_persona: int = 3,
    seeds: list[int] | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run multiple simulations across personas.
    Results saved individually; aggregated summary at end.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    batch_id = f"batch-{int(time.time())}"
    batch_dir = RESULTS_DIR / batch_id
    batch_dir.mkdir(exist_ok=True)

    manifest_path = batch_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)

    all_results: list[SimulationResult] = []
    total = len(personas) * runs_per_persona

    console.print(f"[bold]Batch: {batch_id}[/bold]")
    console.print(f"Personas: {personas}, {runs_per_persona} runs each, {days} days")
    console.print(f"Total simulations: {total}\n")

    run_idx = 0
    for persona in personas:
        for run_num in range(runs_per_persona):
            run_idx += 1
            seed = seeds[run_idx - 1] if seeds and run_idx <= len(seeds) else run_num + 1
            run_key = f"{persona}-run{run_num}-seed{seed}"

            # Skip if already completed (resumability)
            if run_key in manifest.get("completed", {}):
                console.print(f"[dim][{run_idx}/{total}] {run_key} — already done, skipping[/dim]")
                result_path = manifest["completed"][run_key]
                if Path(result_path).exists():
                    data = json.loads(Path(result_path).read_text())
                    all_results.append(SimulationResult(**data))
                continue

            console.print(
                f"\n[bold][{run_idx}/{total}] {persona} run {run_num + 1} (seed={seed})[/bold]"
            )

            try:
                t0 = time.monotonic()
                result = await run_simulation(persona, days, seed, verbose)
                elapsed = time.monotonic() - t0

                all_results.append(result)

                # Record in manifest
                manifest.setdefault("completed", {})[run_key] = str(
                    RESULTS_DIR / f"sim-{persona}-*.json"
                )
                manifest["last_run"] = run_key
                manifest["elapsed_total_s"] = manifest.get("elapsed_total_s", 0) + elapsed
                _save_manifest(manifest_path, manifest)

                console.print(
                    f"[green]Done in {elapsed:.0f}s — "
                    f"score: {result.evaluation.overall_score:.1f}[/green]"
                )

            except Exception as e:
                logger.error("batch_run_failed", persona=persona, run=run_num, error=str(e))
                console.print(f"[red]FAILED: {e}[/red]")
                manifest.setdefault("failed", []).append({"key": run_key, "error": str(e)})
                _save_manifest(manifest_path, manifest)

    # Aggregate results
    summary = _aggregate(all_results, personas)
    summary_path = batch_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    _display_aggregate(summary)

    console.print(f"\n[dim]Batch results: {batch_dir}[/dim]")
    console.print(f"[dim]Summary: {summary_path}[/dim]")

    return summary


def _aggregate(results: list[SimulationResult], personas: list[str]) -> dict:
    """Aggregate evaluation scores across runs."""
    summary: dict = {"personas": {}, "overall": {}}

    for persona in personas:
        runs = [r for r in results if r.persona == persona]
        if not runs:
            continue

        scores_by_dim: dict[str, list[float]] = {}
        perfs: dict[str, list[float]] = {}

        for r in runs:
            for dim, score in r.evaluation.scores.items():
                scores_by_dim.setdefault(dim, []).append(score)
            for t in r.turns:
                phases = ["ingest_ms", "retrieval_ms", "reasoning_ms", "feedback_ms", "total_ms"]
                for phase in phases:
                    val = getattr(t.perf, phase, 0)
                    if val > 0:
                        perfs.setdefault(phase, []).append(val)

        persona_summary = {
            "runs": len(runs),
            "total_turns": sum(len(r.turns) for r in runs),
            "scores": {},
            "perf": {},
        }

        for dim, vals in scores_by_dim.items():
            persona_summary["scores"][dim] = {
                "mean": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
                "std": _std(vals),
            }

        for phase, vals in perfs.items():
            persona_summary["perf"][phase.replace("_ms", "")] = {
                "mean_ms": sum(vals) / len(vals),
                "p50_ms": sorted(vals)[len(vals) // 2],
                "p95_ms": sorted(vals)[int(len(vals) * 0.95)] if len(vals) > 1 else vals[0],
                "max_ms": max(vals),
            }

        overall_scores = [
            r.evaluation.overall_score for r in runs if r.evaluation.overall_score > 0
        ]
        if overall_scores:
            persona_summary["overall_score"] = {
                "mean": sum(overall_scores) / len(overall_scores),
                "min": min(overall_scores),
                "max": max(overall_scores),
            }

        summary["personas"][persona] = persona_summary

    # Global aggregates
    all_scores = [r.evaluation.overall_score for r in results if r.evaluation.overall_score > 0]
    if all_scores:
        summary["overall"] = {
            "mean_score": sum(all_scores) / len(all_scores),
            "total_runs": len(results),
            "total_turns": sum(len(r.turns) for r in results),
        }

    return summary


def _display_aggregate(summary: dict) -> None:
    console.print("\n[bold]Batch Summary[/bold]")

    for persona, data in summary.get("personas", {}).items():
        table = Table(title=f"{persona} ({data['runs']} runs, {data['total_turns']} turns)")
        table.add_column("Dimension", style="bold")
        table.add_column("Mean")
        table.add_column("Min")
        table.add_column("Max")
        table.add_column("Std")

        for dim, stats in data.get("scores", {}).items():
            color = "green" if stats["mean"] >= 7 else "yellow" if stats["mean"] >= 5 else "red"
            table.add_row(
                dim,
                f"[{color}]{stats['mean']:.1f}[/{color}]",
                f"{stats['min']:.1f}",
                f"{stats['max']:.1f}",
                f"{stats['std']:.2f}",
            )

        if "overall_score" in data:
            table.add_row(
                "OVERALL",
                f"[bold]{data['overall_score']['mean']:.1f}[/bold]",
                f"{data['overall_score']['min']:.1f}",
                f"{data['overall_score']['max']:.1f}",
                "",
            )
        console.print(table)

        # Perf table
        if data.get("perf"):
            ptable = Table(title=f"{persona} Performance")
            ptable.add_column("Phase", style="bold")
            ptable.add_column("Mean")
            ptable.add_column("P50")
            ptable.add_column("P95")
            ptable.add_column("Max")
            for phase, stats in data["perf"].items():
                ptable.add_row(
                    phase,
                    f"{stats['mean_ms']:.0f}ms",
                    f"{stats['p50_ms']:.0f}ms",
                    f"{stats['p95_ms']:.0f}ms",
                    f"{stats['max_ms']:.0f}ms",
                )
            console.print(ptable)


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return variance**0.5


def _load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2))
