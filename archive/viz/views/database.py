"""Database view — schema browser and access map."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from viz.components.file_viewer import file_ref_buttons, show_file_panel
from viz.components.mermaid import render_mermaid
from viz.data import JOB_DB_ACCESS, TOOL_DB_ACCESS, gen_db_access_map


def _get_accessors(
    table_name: str,
) -> tuple[list[str], list[str]]:
    """Get sorted reader and writer lists for a table."""
    readers: set[str] = set()
    writers: set[str] = set()
    for tool, access in TOOL_DB_ACCESS.items():
        if table_name in access.get("reads", []):
            readers.add(tool)
        if table_name in access.get("writes", []):
            writers.add(tool)
    for job, access in JOB_DB_ACCESS.items():
        if table_name in access.get("reads", []):
            readers.add(f"job:{job}")
        if table_name in access.get("writes", []):
            writers.add(f"job:{job}")
    return sorted(readers), sorted(writers)


def render(configs: dict, tables: dict, graph: dict, _matrix: list) -> None:
    st.header("Database Access")

    tab_map, tab_schema = st.tabs(["Access Map", "Schema Browser"])

    with tab_map:
        st.caption(
            "Shows all tables and which tools/jobs read and write them. "
            "Core tables show both readers and writers; secondary tables show writers only."
        )
        mermaid = gen_db_access_map(tables, graph, configs)
        render_mermaid(mermaid, height=800, key="db_map")
        selected = file_ref_buttons(mermaid, key_prefix="dbmap")
        show_file_panel(selected)

    with tab_schema:
        st.caption("Browse table schemas with column types, readers, and writers")

        # Search
        search = st.text_input(
            "Search tables or columns",
            key="db_search",
            placeholder="e.g. items, urgency_score",
        )

        # Core tables first, then secondary
        core = [
            "items",
            "messages",
            "user_profiles",
            "item_events",
            "memories",
            "entities",
            "memory_nodes",
            "memory_edges",
            "node_neighbors",
        ]
        secondary = [t for t in sorted(tables.keys()) if t not in core]
        all_tables = [t for t in core if t in tables] + secondary

        for tname in all_tables:
            cols = tables[tname]
            readers, writers = _get_accessors(tname)

            # Apply search filter
            if search:
                matches_table = search.lower() in tname.lower()
                matches_col = any(search.lower() in c["name"].lower() for c in cols)
                if not matches_table and not matches_col:
                    continue

            with st.expander(
                f"**{tname}** — {len(cols)} columns, "
                f"{len(readers)} readers, {len(writers)} writers"
            ):
                # Columns table
                col_rows = [{"Column": c["name"], "Type": c["type"]} for c in cols]
                st.dataframe(
                    pd.DataFrame(col_rows),
                    width="stretch",
                    hide_index=True,
                    height=min(len(col_rows) * 35 + 38, 400),
                )

                # Readers and writers
                r_col, w_col = st.columns(2)
                with r_col:
                    st.markdown("**Readers**")
                    if readers:
                        for r in readers:
                            st.markdown(f"- `{r}`")
                    else:
                        st.markdown("_None tracked_")
                with w_col:
                    st.markdown("**Writers**")
                    if writers:
                        for w in writers:
                            st.markdown(f"- `{w}`")
                    else:
                        st.markdown("_None tracked_")

        # Redis section
        st.divider()
        st.subheader("Redis (Upstash)")
        redis_data = [
            {
                "Key Pattern": "rate:user:{user_id}:{date}",
                "TTL": "24h",
                "Purpose": "Daily rate limit counter",
            },
            {
                "Key Pattern": "session:{user_id}:{key}",
                "TTL": "1h",
                "Purpose": "Session cache (context, state)",
            },
            {
                "Key Pattern": "cache:{key}",
                "TTL": "30d",
                "Purpose": "Long-lived cache (variant assignments)",
            },
        ]
        st.dataframe(
            pd.DataFrame(redis_data), width="stretch", hide_index=True
        )
