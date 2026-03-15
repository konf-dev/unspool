"""Message Flow view — the hot path from user message to response."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from viz.components.file_viewer import file_ref_buttons, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import gen_message_flow


def render(configs: dict, _tables: dict, graph: dict, _matrix: list) -> None:
    st.header("Message Flow")
    st.caption(
        "Every user message follows this path: "
        "rate limit → classify intent → assemble context → pipeline → stream → save → post-process"
    )

    mermaid = gen_message_flow(configs, graph)
    render_mermaid(mermaid, height=700, key="msg_flow")

    # Color legend
    cols = st.columns(5)
    cols[0].markdown(
        '<span style="color:#5dcaa5">■</span> LLM call', unsafe_allow_html=True
    )
    cols[1].markdown(
        '<span style="color:#5588cc">■</span> Tool call', unsafe_allow_html=True
    )
    cols[2].markdown(
        '<span style="color:#cc8855">■</span> Async/background',
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        '<span style="color:#cc5555">■</span> Error path', unsafe_allow_html=True
    )
    cols[4].markdown(
        '<span style="color:#8888cc">■</span> Router/config', unsafe_allow_html=True
    )

    st.divider()

    # Intent routing table
    st.subheader("Intent Routing")
    intents = configs["intents"].get("intents", {})
    rows = []
    for name, info in intents.items():
        rows.append(
            {
                "Intent": name,
                "Description": info.get("description", ""),
                "Pipeline": info.get("pipeline", name),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Key system info
    st.subheader("Key Behaviors")
    c1, c2, c3 = st.columns(3)
    c1.metric("Pipeline Timeout", "60s")
    c2.metric("Rate Limiting", "Fail-open")
    c3.metric("Response Streaming", "SSE")

    st.info(
        "**Error handling:** TimeoutError and Exception both send an error message "
        "to the user via SSE and save with `metadata.error=true`. "
        "The server never hangs or returns 500."
    )

    # File references
    selected = file_ref_buttons(mermaid, key_prefix="msgflow")
    show_file_panel(selected)
