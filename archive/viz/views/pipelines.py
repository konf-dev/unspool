"""Pipeline detail view — step-by-step breakdown of each pipeline."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from viz.components.file_viewer import file_ref_buttons, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import JOB_DB_ACCESS, TOOL_DB_ACCESS, gen_pipeline_detail


def render(configs: dict, _tables: dict, graph: dict, _matrix: list) -> None:
    st.header("Pipeline Details")

    pipeline_names = sorted(configs["pipelines"].keys())
    selected = st.sidebar.selectbox("Pipeline", pipeline_names, key="pipe_select")
    if not selected:
        return

    pdata = configs["pipelines"][selected]
    ctx = graph["pipeline_context"].get(selected, {})
    description = pdata.get("description", "")

    if description:
        st.caption(description)

    # Mermaid diagram
    mermaid = gen_pipeline_detail(selected, pdata, ctx)
    render_mermaid(mermaid, height=450, key=f"pipe_{selected}")

    st.divider()

    # Steps detail table
    steps = pdata.get("steps", [])
    if steps:
        st.subheader("Steps")
        rows = []
        for step in steps:
            tool = step.get("tool", "")
            db_writes = (
                ", ".join(TOOL_DB_ACCESS.get(tool, {}).get("writes", []))
                if tool
                else ""
            )
            db_reads = (
                ", ".join(TOOL_DB_ACCESS.get(tool, {}).get("reads", [])) if tool else ""
            )
            rows.append(
                {
                    "Step": step["id"],
                    "Type": step.get("type", ""),
                    "Prompt / Tool": step.get("prompt", "") or step.get("tool", ""),
                    "Output Schema": step.get("output_schema", ""),
                    "Stream": "yes" if step.get("stream") else "",
                    "DB Reads": db_reads,
                    "DB Writes": db_writes,
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Context loaded
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Context Loaded")
        required = ctx.get("required", [])
        optional = ctx.get("optional", [])
        if required:
            st.markdown("**Required:** " + ", ".join(f"`{r}`" for r in required))
        if optional:
            st.markdown("**Optional:** " + ", ".join(f"`{o}`" for o in optional))
        if not required and not optional:
            st.markdown("_No context loaded_")

    with col2:
        # Post-processing
        st.subheader("Post-Processing")
        pp = pdata.get("post_processing", [])
        if pp:
            for p in pp:
                job = p.get("job", "")
                delay = p.get("delay", "")
                db_writes = JOB_DB_ACCESS.get(job, {}).get("writes", [])
                st.markdown(
                    f"**{job}** (delay: {delay})\n\n"
                    f"Writes: {', '.join(f'`{t}`' for t in db_writes) if db_writes else 'none'}"
                )
        else:
            st.markdown("_None_")

    # Variable flow
    has_vars = False
    for step in steps:
        inputs = step.get("input") or {}
        for var_name, var_ref in inputs.items():
            if isinstance(var_ref, str) and "${" in var_ref:
                if not has_vars:
                    st.divider()
                    st.subheader("Variable Flow")
                    has_vars = True
                st.markdown(f"- `{step['id']}.{var_name}` ← `{var_ref}`")

    # File references
    selected_file = file_ref_buttons(mermaid, key_prefix=f"pipe_{selected}")
    show_file_panel(selected_file)
