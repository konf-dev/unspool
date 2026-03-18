"""Post-generation corpus validation."""

import json
from pathlib import Path

import structlog
from graph_lab.corpus.types import CorpusMessage, DayMarker
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()


def _read_corpus(path: Path) -> tuple[list[CorpusMessage], list[DayMarker]]:
    """Read a JSONL corpus file into messages and markers."""
    messages: list[CorpusMessage] = []
    markers: list[DayMarker] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("type") == "day_marker":
                markers.append(DayMarker(**data))
            else:
                messages.append(CorpusMessage(**data))
    return messages, markers


def validate_corpus_file(path: Path) -> dict:
    """Validate a single JSONL corpus file. Returns a report dict."""
    messages, markers = _read_corpus(path)
    persona = path.stem
    issues: list[str] = []

    # Message count
    msg_count = len(messages)
    if msg_count == 0:
        issues.append("No messages generated")

    # Check day sequencing
    all_days = sorted({m.day for m in messages} | {m.day for m in markers})
    if all_days and all_days[0] != 1:
        issues.append(f"First day is {all_days[0]}, expected 1")

    # Consecutive identical messages
    for i in range(1, len(messages)):
        if messages[i].content == messages[i - 1].content:
            issues.append(
                f"Consecutive identical messages at day {messages[i].day}: "
                f"'{messages[i].content[:50]}...'"
            )

    # ID uniqueness
    ids = [m.id for m in messages] + [m.id for m in markers]
    if len(ids) != len(set(ids)):
        issues.append("Duplicate IDs found")

    # Message length distribution
    lengths = [len(m.content) for m in messages]
    avg_len = sum(lengths) / len(lengths) if lengths else 0

    # Scenario coverage
    scenario_tags = {m.scenario_tag for m in messages if m.scenario_tag}

    # Skipped days
    skipped = sum(1 for m in markers if m.skipped)

    return {
        "persona": persona,
        "path": str(path),
        "message_count": msg_count,
        "day_marker_count": len(markers),
        "skipped_days": skipped,
        "unique_days_with_messages": len({m.day for m in messages}),
        "avg_message_length": round(avg_len, 1),
        "min_message_length": min(lengths) if lengths else 0,
        "max_message_length": max(lengths) if lengths else 0,
        "scenario_tags": sorted(scenario_tags),
        "scenario_count": len(scenario_tags),
        "models_used": sorted({m.generation_model for m in messages}),
        "issues": issues,
        "valid": len(issues) == 0,
    }


def validate_corpus_dir(corpus_dir: Path) -> list[dict]:
    """Validate all JSONL files in a corpus directory."""
    reports: list[dict] = []

    jsonl_files = sorted(corpus_dir.glob("*.jsonl"))
    if not jsonl_files:
        console.print(f"[red]No .jsonl files found in {corpus_dir}[/red]")
        return reports

    # Collect all scenario tags across all files
    all_scenario_tags: set[str] = set()

    for path in jsonl_files:
        report = validate_corpus_file(path)
        reports.append(report)
        all_scenario_tags.update(report["scenario_tags"])

    # Display results
    table = Table(title=f"Corpus Validation — {corpus_dir.name}")
    table.add_column("Persona", style="bold")
    table.add_column("Messages")
    table.add_column("Days")
    table.add_column("Skipped")
    table.add_column("Avg Len")
    table.add_column("Scenarios")
    table.add_column("Status")

    for r in reports:
        status = "[green]OK[/green]" if r["valid"] else f"[red]{len(r['issues'])} issues[/red]"
        table.add_row(
            r["persona"],
            str(r["message_count"]),
            str(r["unique_days_with_messages"]),
            str(r["skipped_days"]),
            str(r["avg_message_length"]),
            str(r["scenario_count"]),
            status,
        )
    console.print(table)

    # Show scenario coverage
    total_msgs = sum(r["message_count"] for r in reports)
    console.print(f"\nTotal messages: {total_msgs}")
    console.print(f"Unique scenario tags found: {len(all_scenario_tags)}")
    if all_scenario_tags:
        console.print(f"Scenarios: {', '.join(sorted(all_scenario_tags))}")

    # Show issues
    all_issues = [(r["persona"], issue) for r in reports for issue in r["issues"]]
    if all_issues:
        console.print(f"\n[red]Issues ({len(all_issues)}):[/red]")
        for persona, issue in all_issues:
            console.print(f"  [{persona}] {issue}")
    else:
        console.print("\n[green]All files valid.[/green]")

    return reports
