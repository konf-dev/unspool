"""Proactive Messages view — trigger chain evaluated on app open."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from viz.components.file_viewer import file_ref_buttons, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import gen_proactive_flow


def render(configs: dict, _tables: dict, _graph: dict, _matrix: list) -> None:
    st.header("Proactive Messages")
    st.caption(
        "Evaluated in priority order when the user opens the app. "
        "Only the first matching trigger fires per session."
    )

    mermaid = gen_proactive_flow(configs)
    render_mermaid(mermaid, height=650, key="proactive")

    st.divider()

    # Triggers detail table
    st.subheader("Trigger Details")
    triggers = configs["proactive"].get("triggers", {})
    rows = []
    for tname, tdata in sorted(
        triggers.items(), key=lambda x: x[1].get("priority", 99)
    ):
        params = tdata.get("params", {})
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        rows.append(
            {
                "Priority": tdata.get("priority", ""),
                "Trigger": tname,
                "Description": tdata.get("description", ""),
                "Condition": tdata.get("condition", ""),
                "Params": param_str,
                "Prompt": tdata.get("prompt", ""),
                "Enabled": "yes" if tdata.get("enabled", True) else "no",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.info(
        "**Max 1 push notification per day** — `notification_sent_today` flag in "
        "`user_profiles` is reset daily by the `reset_notifications` job. "
        "Proactive messages are saved with `metadata.type = proactive`."
    )

    selected = file_ref_buttons(mermaid, key_prefix="proactive")
    show_file_panel(selected)
