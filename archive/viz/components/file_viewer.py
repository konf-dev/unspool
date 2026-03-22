"""Inline file viewer with syntax highlighting."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from viz.data import extract_file_refs, lang_for_file, read_source_file


def file_viewer(rel_path: str) -> None:
    """Display a source file with syntax highlighting."""
    content = read_source_file(rel_path)
    if content is None:
        st.warning(f"File not found: `{rel_path}`")
        return

    lang = lang_for_file(rel_path)
    st.caption(f"`{rel_path}`")
    st.code(content, language=lang, line_numbers=True)


def file_ref_buttons(mermaid_str: str, key_prefix: str = "ref") -> str | None:
    """Show buttons for all files referenced in a Mermaid diagram.

    Returns the relative path of the clicked file, or None.
    """
    refs = extract_file_refs(mermaid_str)
    if not refs:
        return None

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_refs: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            unique_refs.append(r)

    selected = None
    with st.expander(f"Referenced files ({len(unique_refs)})", expanded=False):
        for i, ref in enumerate(unique_refs):
            filename = Path(ref).name
            file_type = Path(ref).suffix.lstrip(".")
            if st.button(
                f"{filename}  `{file_type}`",
                key=f"{key_prefix}_{i}",
                width="stretch",
            ):
                selected = ref

    return selected


def show_file_panel(rel_path: str | None) -> None:
    """Show file viewer panel if a file is selected."""
    if not rel_path:
        return
    st.divider()
    file_viewer(rel_path)
