#!/usr/bin/env python3
"""Generate Mermaid flow diagrams as markdown files in viz/flows/.

GitHub renders Mermaid code blocks natively, so these files are viewable
directly on the GitHub website.

Usage:
    python viz/generate.py           # Generate all
    python viz/generate.py --check   # CI: fail if output differs from committed
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from generate_flows import (
    build_dependency_graph,
    build_impact_matrix,
    gen_background_jobs,
    gen_config_deps,
    gen_db_access_map,
    gen_message_flow,
    gen_pipeline_detail,
    gen_proactive_flow,
    gen_impact_matrix_md,
    load_all_configs,
    parse_table_schemas,
)

FLOWS_DIR = Path(__file__).resolve().parent / "flows"


def _wrap(title: str, description: str, mermaid: str) -> str:
    return f"# {title}\n\n{description}\n\n```mermaid\n{mermaid}\n```\n"


def generate(out_dir: Path) -> list[Path]:
    """Generate all flow markdown files into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    configs = load_all_configs()
    tables = parse_table_schemas()
    graph = build_dependency_graph(configs)
    matrix = build_impact_matrix(configs, graph)

    written: list[Path] = []

    def write(name: str, content: str) -> None:
        p = out_dir / name
        p.write_text(content)
        written.append(p)

    write(
        "message_flow.md",
        _wrap(
            "Message Flow",
            "Every user message follows this path: rate limit → classify → context → pipeline → stream → save → post-process.",
            gen_message_flow(configs, graph),
        ),
    )

    for pname, pdata in sorted(configs["pipelines"].items()):
        ctx = graph["pipeline_context"].get(pname, {})
        desc = pdata.get("description", "")
        write(
            f"pipeline_{pname}.md",
            _wrap(f"Pipeline: {pname}", desc, gen_pipeline_detail(pname, pdata, ctx)),
        )

    write(
        "background_jobs.md",
        _wrap(
            "Background Jobs",
            "All jobs triggered by QStash cron or event dispatch.",
            gen_background_jobs(configs),
        ),
    )

    write(
        "database_access.md",
        _wrap(
            "Database Access Map",
            "Tables and which tools/jobs read/write them.",
            gen_db_access_map(tables, graph, configs),
        ),
    )

    write(
        "proactive_flow.md",
        _wrap(
            "Proactive Messages",
            "Evaluated in priority order when user opens the app. First match fires.",
            gen_proactive_flow(configs),
        ),
    )

    write(
        "config_dependencies.md",
        _wrap(
            "Config Dependencies",
            "Which config files affect which pipelines, tools, and jobs.",
            gen_config_deps(configs, graph),
        ),
    )

    write("impact_matrix.md", gen_impact_matrix_md(matrix))

    # Index file linking to all diagrams
    index_lines = ["# Architecture Flows\n", "Auto-generated from config files. Run `python viz/generate.py` to regenerate.\n"]
    for f in sorted(written, key=lambda p: p.name):
        title = f.stem.replace("_", " ").title()
        index_lines.append(f"- [{title}]({f.name})")
    index_lines.append("")
    write("README.md", "\n".join(index_lines))

    return written


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate flow diagrams to viz/flows/")
    parser.add_argument("--check", action="store_true", help="CI: fail if output differs")
    args = parser.parse_args()

    if args.check:
        old_hashes: dict[str, str] = {}
        if FLOWS_DIR.exists():
            for f in FLOWS_DIR.iterdir():
                if f.suffix == ".md":
                    old_hashes[f.name] = _hash(f)

        with tempfile.TemporaryDirectory() as tmpdir:
            written = generate(Path(tmpdir))
            new_hashes = {f.name: _hash(f) for f in written}

        if old_hashes != new_hashes:
            changed = [k for k in new_hashes if old_hashes.get(k) != new_hashes[k]]
            print(f"Flow diagrams are stale. Changed: {', '.join(sorted(changed))}")
            print("Run: python viz/generate.py")
            sys.exit(1)
        print("Flow diagrams are up to date.")
        sys.exit(0)

    written = generate(FLOWS_DIR)
    print(f"Generated {len(written)} files in viz/flows/")
    for f in written:
        print(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
