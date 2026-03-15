#!/usr/bin/env python3
"""Unspool Architecture Dashboard.

Run with:
    streamlit run viz/app.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure project root is on sys.path so `viz.*` imports work
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st  # noqa: E402

from viz.data import ROOT, load_data  # noqa: E402
from viz.views import (  # noqa: E402
    config_deps,
    database,
    impact,
    jobs,
    message_flow,
    pipelines,
    proactive,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Unspool Architecture",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """<style>
    .block-container { padding-top: 1rem; max-width: 100%; }
    [data-testid="stSidebar"] { min-width: 220px; }
    .stMetric { background: #1a1a1f; padding: 12px; border-radius: 8px; }
    iframe { border-radius: 8px; }
</style>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("Unspool")
st.sidebar.caption("Architecture Dashboard")
st.sidebar.divider()

# Navigation
VIEWS = {
    "Overview": None,
    "Message Flow": message_flow,
    "Pipelines": pipelines,
    "Background Jobs": jobs,
    "Database": database,
    "Proactive Messages": proactive,
    "Config Dependencies": config_deps,
    "Impact Matrix": impact,
}

view_name = st.sidebar.radio(
    "View",
    list(VIEWS.keys()),
    label_visibility="collapsed",
)

st.sidebar.divider()

# Regenerate button
if st.sidebar.button("🔄 Regenerate from configs"):
    with st.sidebar.status("Regenerating..."):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "generate_flows.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            st.sidebar.success("Regenerated successfully")
            load_data.clear()
            st.rerun()
        else:
            st.sidebar.error(f"Error: {result.stderr}")

# Reload cache
if st.sidebar.button("🗑️ Clear cache"):
    load_data.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

configs, tables, graph, matrix = load_data()

# ---------------------------------------------------------------------------
# Overview page
# ---------------------------------------------------------------------------


def render_overview() -> None:
    st.header("Unspool Architecture")
    st.caption("Auto-generated from config files and SQL migrations")

    # Stats
    cols = st.columns(7)
    cols[0].metric("Pipelines", len(configs.get("pipelines", {})))
    cols[1].metric("Intents", len(configs.get("intents", {}).get("intents", {})))

    all_prompts: set[str] = set()
    for steps in graph.get("pipeline_steps", {}).values():
        for step in steps:
            if step.get("prompt"):
                all_prompts.add(step["prompt"])
    cols[2].metric("Prompts", len(all_prompts))

    all_tools: set[str] = set()
    for steps in graph.get("pipeline_steps", {}).values():
        for step in steps:
            if step.get("tool"):
                all_tools.add(step["tool"])
    cols[3].metric("Tools", len(all_tools))
    cols[4].metric("DB Tables", len(tables))
    cols[5].metric("Cron Jobs", len(configs.get("jobs", {}).get("cron_jobs", {})))
    cols[6].metric(
        "Proactive Triggers",
        len(configs.get("proactive", {}).get("triggers", {})),
    )

    st.divider()

    # Color legend
    st.subheader("Color Legend")
    legend_cols = st.columns(5)
    legend_cols[0].markdown(
        '<span style="color:#5dcaa5;font-size:20px">■</span> **LLM call** — AI model invocation',
        unsafe_allow_html=True,
    )
    legend_cols[1].markdown(
        '<span style="color:#5588cc;font-size:20px">■</span> **Tool call** — Python function',
        unsafe_allow_html=True,
    )
    legend_cols[2].markdown(
        '<span style="color:#cc8855;font-size:20px">■</span> **Async** — background/post-processing',
        unsafe_allow_html=True,
    )
    legend_cols[3].markdown(
        '<span style="color:#cc5555;font-size:20px">■</span> **Error** — error paths',
        unsafe_allow_html=True,
    )
    legend_cols[4].markdown(
        '<span style="color:#8888cc;font-size:20px">■</span> **Config/Router** — routing decisions',
        unsafe_allow_html=True,
    )

    st.divider()

    # Quick navigation
    st.subheader("Quick Navigation")
    nav_cols = st.columns(3)
    with nav_cols[0]:
        st.markdown(
            "**Message Flow** — How every user message is processed from "
            "rate limiting through intent classification to pipeline execution"
        )
        st.markdown(
            "**Pipelines** — Step-by-step breakdown of each pipeline's "
            "LLM calls, tool calls, variable flow, and DB access"
        )
        st.markdown(
            "**Background Jobs** — All cron-scheduled and event-triggered "
            "jobs with their schedules and DB access patterns"
        )
    with nav_cols[1]:
        st.markdown(
            "**Database** — Schema browser showing all 13 Postgres tables "
            "and Redis key patterns, plus who reads/writes each table"
        )
        st.markdown(
            "**Proactive Messages** — The priority-ordered trigger chain "
            "evaluated when a user opens the app"
        )
    with nav_cols[2]:
        st.markdown(
            "**Config Dependencies** — How config files connect to "
            "pipelines, tools, and jobs — what changes affect what"
        )
        st.markdown(
            "**Impact Matrix** — Searchable reverse dependency table: "
            "if you change a file, what flows and DB tables are affected?"
        )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

if view_name == "Overview":
    render_overview()
else:
    view_module = VIEWS[view_name]
    if view_module:
        view_module.render(configs, tables, graph, matrix)
