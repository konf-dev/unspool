"""Data loading and caching for the architecture dashboard.

Imports all data functions from tools/generate_flows.py and adds
Streamlit caching on top.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from generate_flows import (  # noqa: E402
    CONTEXT_LOADER_TABLES,
    JOB_DB_ACCESS,
    SCORING_CONSUMERS,
    TOOL_DB_ACCESS,
    build_dependency_graph,
    build_impact_matrix,
    gen_background_jobs,
    gen_config_deps,
    gen_db_access_map,
    gen_message_flow,
    gen_pipeline_detail,
    gen_proactive_flow,
    load_all_configs,
    parse_table_schemas,
)

# Re-export everything views need
__all__ = [
    "ROOT",
    "TOOL_DB_ACCESS",
    "JOB_DB_ACCESS",
    "SCORING_CONSUMERS",
    "CONTEXT_LOADER_TABLES",
    "load_data",
    "read_source_file",
    "extract_file_refs",
    "gen_message_flow",
    "gen_pipeline_detail",
    "gen_background_jobs",
    "gen_db_access_map",
    "gen_proactive_flow",
    "gen_config_deps",
]


@st.cache_data
def load_data() -> tuple[dict, dict, dict, list[dict[str, str]]]:
    """Load all configs, parse schemas, build graphs. Cached per session."""
    configs = load_all_configs()
    tables = parse_table_schemas()
    graph = build_dependency_graph(configs)
    matrix = build_impact_matrix(configs, graph)
    return configs, tables, graph, matrix


def read_source_file(rel_path: str) -> str | None:
    """Read a source file from the repo by relative path."""
    full = ROOT / rel_path
    if full.exists() and full.is_file():
        return full.read_text()
    return None


def extract_file_refs(mermaid_str: str) -> list[str]:
    """Extract relative file paths from Mermaid click directives."""
    return re.findall(r'click \w+ "([^"]+)"', mermaid_str)


def lang_for_file(path: str) -> str:
    """Return syntax highlighting language for a file extension."""
    ext = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".sql": "sql",
        ".toml": "toml",
        ".json": "json",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".css": "css",
        ".html": "html",
    }.get(ext, "text")
