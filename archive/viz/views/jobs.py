"""Background Jobs view — cron-scheduled and event-triggered jobs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from viz.components.file_viewer import file_ref_buttons, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import JOB_DB_ACCESS, gen_background_jobs


def render(configs: dict, _tables: dict, _graph: dict, _matrix: list) -> None:
    st.header("Background Jobs")
    st.caption("Cron-scheduled jobs via QStash and event-triggered post-processing")

    mermaid = gen_background_jobs(configs)
    render_mermaid(mermaid, height=600, key="jobs")

    st.divider()

    # Jobs detail table
    st.subheader("Cron Jobs")
    cron_jobs = configs["jobs"].get("cron_jobs", {})
    rows = []
    for job_name, job_data in cron_jobs.items():
        py_name = job_name.replace("-", "_")
        access = JOB_DB_ACCESS.get(py_name, {})
        rows.append(
            {
                "Job": py_name,
                "Schedule": job_data.get("schedule", ""),
                "DB Reads": ", ".join(access.get("reads", [])),
                "DB Writes": ", ".join(access.get("writes", [])),
                "Source": f"backend/src/jobs/{py_name}.py",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Event-triggered
    st.subheader("Event-Triggered Jobs")
    pc = JOB_DB_ACCESS.get("process_conversation", {})
    st.markdown(
        f"**process_conversation** — triggered 10s after chat "
        f"(pipelines: brain_dump)\n\n"
        f"- Reads: {', '.join(f'`{t}`' for t in pc.get('reads', []))}\n"
        f"- Writes: {', '.join(f'`{t}`' for t in pc.get('writes', []))}\n"
        f"- Does: embeddings, entity extraction, memory extraction"
    )
    pg = JOB_DB_ACCESS.get("process_graph", {})
    st.markdown(
        f"**process_graph** — triggered 5s after chat "
        f"(pipelines: brain_dump, status_done, conversation, emotional)\n\n"
        f"- Reads: {', '.join(f'`{t}`' for t in pg.get('reads', []))}\n"
        f"- Writes: {', '.join(f'`{t}`' for t in pg.get('writes', []))}\n"
        f"- Does: graph node/edge ingest, embedding generation, feedback detection"
    )

    # Dispatch map
    dispatch = configs["jobs"].get("dispatch_map", {})
    if dispatch:
        st.subheader("Dispatch Map")
        st.markdown(
            "Maps pipeline `post_processing` job names to `/jobs/` endpoint paths:"
        )
        for job, endpoint in dispatch.items():
            st.markdown(f"- `{job}` → `POST /jobs/{endpoint}`")

    selected = file_ref_buttons(mermaid, key_prefix="jobs")
    show_file_panel(selected)
