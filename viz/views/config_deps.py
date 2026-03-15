"""Config Dependencies view — how config files connect to everything."""

from __future__ import annotations

import streamlit as st

from viz.components.file_viewer import file_ref_buttons, file_viewer, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import gen_config_deps


CONFIG_DESCRIPTIONS = {
    "intents.yaml": "Maps user intents to pipelines. Each intent has a description and a pipeline name.",
    "context_rules.yaml": "Per-intent rules for what data to load before pipeline execution (profile, messages, items, etc).",
    "scoring.yaml": "Thresholds and parameters for urgency decay, momentum, item selection, rescheduling, fuzzy matching, notifications.",
    "gate.yaml": "Rate limiting configuration — message counts for free and paid tiers.",
    "jobs.yaml": "Cron schedules for background jobs and the dispatch map for post-processing.",
    "proactive.yaml": "Proactive message triggers — conditions, priorities, and prompt files.",
    "patterns.yaml": "Pattern detection analyses — behavioral patterns, preferences, memory consolidation.",
    "variants.yaml": "A/B test variant definitions (currently empty).",
}


def render(configs: dict, _tables: dict, graph: dict, _matrix: list) -> None:
    st.header("Config Dependencies")
    st.caption(
        "How config files connect to pipelines, tools, and background jobs. "
        "Change a config → these flows are affected."
    )

    mermaid = gen_config_deps(configs, graph)
    render_mermaid(mermaid, height=750, key="config_deps")

    st.divider()

    # Per-config details
    st.subheader("Config Files")

    config_files = [
        "intents.yaml",
        "context_rules.yaml",
        "scoring.yaml",
        "gate.yaml",
        "jobs.yaml",
        "proactive.yaml",
        "patterns.yaml",
        "variants.yaml",
    ]

    selected_file = None
    for cfg in config_files:
        desc = CONFIG_DESCRIPTIONS.get(cfg, "")
        with st.expander(f"**{cfg}** — {desc}"):
            rel_path = f"backend/config/{cfg}"
            if st.button(f"View {cfg}", key=f"cfg_view_{cfg}"):
                selected_file = rel_path

            # Show key values from parsed config
            config_key = cfg.replace(".yaml", "")
            data = configs.get(config_key, {})
            if data:
                st.code(
                    _format_yaml_preview(data),
                    language="yaml",
                )

    # Also show pipeline configs
    st.subheader("Pipeline Configs")
    for pname in sorted(configs["pipelines"]):
        rel_path = f"backend/config/pipelines/{pname}.yaml"
        pdata = configs["pipelines"][pname]
        step_count = len(pdata.get("steps", []))
        desc = pdata.get("description", "")
        with st.expander(f"**{pname}.yaml** — {desc} ({step_count} steps)"):
            if st.button(f"View {pname}.yaml", key=f"pcfg_{pname}"):
                selected_file = rel_path

    if selected_file:
        st.divider()
        file_viewer(selected_file)

    # Mermaid file refs
    mermaid_selected = file_ref_buttons(mermaid, key_prefix="cfgdeps")
    show_file_panel(mermaid_selected)


def _format_yaml_preview(data: dict, max_depth: int = 2) -> str:
    """Format a dict as a readable YAML-like preview, truncated."""
    import yaml

    # Truncate large nested structures
    truncated = _truncate(data, max_depth)
    return yaml.dump(truncated, default_flow_style=False, sort_keys=False)


def _truncate(obj: object, depth: int) -> object:
    if depth <= 0:
        if isinstance(obj, dict):
            return f"{{...{len(obj)} keys}}"
        if isinstance(obj, list):
            return f"[...{len(obj)} items]"
        return obj
    if isinstance(obj, dict):
        return {k: _truncate(v, depth - 1) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > 5:
            return [_truncate(v, depth - 1) for v in obj[:3]] + [
                f"...+{len(obj) - 3} more"
            ]
        return [_truncate(v, depth - 1) for v in obj]
    return obj
