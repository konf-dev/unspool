#!/usr/bin/env python3
"""Generate docs/CONFIG_MAP.md from config files.

Run: python -m scripts.config_map
"""
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
DOCS_DIR = ROOT.parent / "docs"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=ROOT,
        ).decode().strip()
    except Exception:
        return "unknown"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    intents_path = CONFIG_DIR / "intents.yaml"
    context_path = CONFIG_DIR / "context_rules.yaml"

    intents_cfg = _load_yaml(intents_path)
    context_cfg = _load_yaml(context_path)

    intents = intents_cfg.get("intents", {})
    context_rules = context_cfg.get("rules", {})

    # Collect all referenced prompts and tools
    all_referenced_prompts: set[str] = set()
    all_referenced_tools: set[str] = set()

    lines: list[str] = []
    lines.append("# Config Map (auto-generated — do not edit)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Git: {_git_sha()}")
    lines.append("")
    lines.append(f"Intents config: `config/intents.yaml` ({_hash(intents_path)})")
    lines.append(f"Context rules: `config/context_rules.yaml` ({_hash(context_path)})")
    lines.append("")
    lines.append("---")
    lines.append("")

    for intent_name, intent_info in sorted(intents.items()):
        pipeline_name = intent_info.get("pipeline", intent_name)
        pipeline_path = CONFIG_DIR / "pipelines" / f"{pipeline_name}.yaml"

        lines.append(f"## {intent_name}")
        lines.append("")

        if intent_info.get("description"):
            lines.append(f"_{intent_info['description']}_")
            lines.append("")

        if not pipeline_path.exists():
            lines.append(f"Pipeline: `config/pipelines/{pipeline_name}.yaml` — **NOT FOUND**")
            lines.append("")
            continue

        pipeline_hash = _hash(pipeline_path)
        lines.append(f"Pipeline: `config/pipelines/{pipeline_name}.yaml` ({pipeline_hash})")
        lines.append("")

        # Context
        ctx = context_rules.get(intent_name, {})
        load = ctx.get("load", [])
        optional = ctx.get("optional", [])
        ctx_parts = []
        if load:
            ctx_parts.append(", ".join(load))
        if optional:
            ctx_parts.append(f"optional: {', '.join(optional)}")
        if ctx_parts:
            lines.append(f"Context: {' | '.join(ctx_parts)}")
            lines.append("")

        # Steps table
        pipeline_cfg = _load_yaml(pipeline_path)
        steps = pipeline_cfg.get("steps", [])

        lines.append("| Step | Type | Config | Hash |")
        lines.append("|------|------|--------|------|")

        for step in steps:
            step_id = step.get("id", "?")
            step_type = step.get("type", "?")
            stream = step.get("stream", False)
            type_label = f"{step_type} (stream)" if stream else step_type

            config_ref = "—"
            step_hash = "—"

            if step_type == "llm_call" and step.get("prompt"):
                prompt_file = step["prompt"]
                config_ref = f"`prompts/{prompt_file}`"
                all_referenced_prompts.add(prompt_file)
                prompt_path = PROMPTS_DIR / prompt_file
                if prompt_path.exists():
                    step_hash = _hash(prompt_path)
                else:
                    step_hash = "**missing**"
            elif step_type == "tool_call" and step.get("tool"):
                config_ref = step["tool"]
                all_referenced_tools.add(step["tool"])
            elif step_type == "query" and step.get("query"):
                config_ref = f"query: {step['query']}"
            elif step_type == "operation" and step.get("operation"):
                config_ref = f"op: {step['operation']}"
            elif step_type == "branch":
                config_ref = "branch"

            lines.append(f"| {step_id} | {type_label} | {config_ref} | {step_hash} |")

        lines.append("")

        # Post-processing
        post = pipeline_cfg.get("post_processing", [])
        if post:
            jobs = ", ".join(f"{p['job']} ({p.get('delay', '0s')})" for p in post)
            lines.append(f"Post-processing: {jobs}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Orphaned prompts
    all_prompt_files = {p.name for p in PROMPTS_DIR.glob("*.md")}
    orphaned = sorted(all_prompt_files - all_referenced_prompts)

    if orphaned:
        lines.append("## Unreferenced Prompts")
        lines.append("")
        lines.append("These prompt files exist in `prompts/` but are not referenced by any pipeline:")
        lines.append("")
        for p in orphaned:
            prompt_path = PROMPTS_DIR / p
            lines.append(f"- `prompts/{p}` ({_hash(prompt_path)})")
        lines.append("")

    # Config files summary
    lines.append("## Config Files")
    lines.append("")
    lines.append("| File | Hash |")
    lines.append("|------|------|")

    for config_file in sorted(CONFIG_DIR.glob("*.yaml")):
        lines.append(f"| `config/{config_file.name}` | {_hash(config_file)} |")
    for config_file in sorted((CONFIG_DIR / "pipelines").glob("*.yaml")):
        lines.append(f"| `config/pipelines/{config_file.name}` | {_hash(config_file)} |")

    lines.append("")

    output = "\n".join(lines) + "\n"
    out_path = DOCS_DIR / "CONFIG_MAP.md"
    out_path.write_text(output, encoding="utf-8")
    print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
