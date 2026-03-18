"""Streamlit replay viewer — scrub through corpus replays and watch graphs grow."""

import asyncio
import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Graph Lab — Replay Viewer",
    layout="wide",
    page_icon="\U0001f9e0",
)

from graph_lab.src.config import SURREALDB_PASS, SURREALDB_URL, SURREALDB_USER  # noqa: E402
from surrealdb import AsyncSurreal  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"

# --- Palette ---
BG = "#0D0D0F"
SURFACE = "#1A1A1F"
BORDER = "#2A2A30"
TEXT = "#E0E0E0"
TEXT_DIM = "#888"
ACCENT = "#7FCCB0"
USER_CLR = "#5B8DEF"
SCENARIO_CLR = "#E8A845"
NODE_ACTIVE = "#5B8DEF"
EDGE_STRONG = "#7FCCB0"
EDGE_WEAK = "#333"


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _normalize(val):
    """Recursively convert SurrealDB types to plain Python."""
    from surrealdb import RecordID  # noqa: E402
    from datetime import datetime  # noqa: E402

    if isinstance(val, RecordID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _normalize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_normalize(v) for v in val]
    return val


def _rows(result) -> list[dict]:
    if isinstance(result, list):
        return [_normalize(item) for item in result if isinstance(item, dict)]
    return []


async def _query_graph(user_id: str) -> tuple[list[dict], list[dict]]:
    """Fresh connection per query to avoid event loop conflicts."""
    c = AsyncSurreal(SURREALDB_URL)
    await c.connect()
    await c.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})
    await c.use("unspool", "graph_lab")
    try:
        nodes_raw = await c.query(
            "SELECT * FROM node WHERE user_id = $uid",
            {"uid": user_id},
        )
        nodes = _rows(nodes_raw)
        if nodes:
            edges_raw = await c.query(
                "SELECT * FROM edge WHERE user_id = $uid",
                {"uid": user_id},
            )
            edges = _rows(edges_raw)
        else:
            edges = []
        return nodes, edges
    finally:
        await c.close()


def load_replay_files() -> dict[str, Path]:
    replays = {}
    if not RESULTS_DIR.exists():
        return replays
    for f in sorted(RESULTS_DIR.glob("replay-*_turns.jsonl")):
        name = f.stem.replace("_turns", "")
        persona = name.split("-")[1] if "-" in name else name
        replays[persona] = f
    return replays


def load_turns(path: Path) -> list[dict]:
    turns = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                turns.append(json.loads(line))
    return turns


def stat_box(value: str, label: str, color: str = ACCENT) -> str:
    return (
        f'<div class="stat-box">'
        f'<div class="stat-number" style="color:{color}">{value}</div>'
        f'<div class="stat-label">{label}</div></div>'
    )


def tag_span(text: str, css_class: str) -> str:
    return f'<span class="meta-tag {css_class}">{text}</span>'


# --- Custom CSS ---
st.markdown(
    f"""
<style>
    .stApp {{ background-color: {BG}; color: {TEXT}; }}
    .block-container {{ padding-top: 1rem; max-width: 1400px; }}
    div[data-testid="stSidebar"] {{ background-color: {SURFACE}; }}
    .turn-card {{
        background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: 8px; padding: 16px; margin-bottom: 8px;
    }}
    .turn-card.active {{
        border-color: {ACCENT}; box-shadow: 0 0 12px {ACCENT}44;
    }}
    .user-msg {{ color: {USER_CLR}; font-size: 0.95em; line-height: 1.5; }}
    .unspool-msg {{ color: {ACCENT}; font-size: 0.95em; line-height: 1.5; }}
    .meta-tag {{
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 0.75em; font-weight: 600; margin-right: 4px;
    }}
    .tag-scenario {{
        background: {SCENARIO_CLR}33; color: {SCENARIO_CLR};
        border: 1px solid {SCENARIO_CLR}66;
    }}
    .tag-energy {{
        background: {ACCENT}22; color: {ACCENT};
        border: 1px solid {ACCENT}44;
    }}
    .tag-mood {{
        background: {USER_CLR}22; color: {USER_CLR};
        border: 1px solid {USER_CLR}44;
    }}
    .tag-open {{
        background: #9B59B633; color: #9B59B6;
        border: 1px solid #9B59B666;
    }}
    .stat-box {{
        text-align: center; padding: 12px; background: {SURFACE};
        border: 1px solid {BORDER}; border-radius: 8px;
    }}
    .stat-number {{ font-size: 1.8em; font-weight: 700; color: {ACCENT}; }}
    .stat-label {{
        font-size: 0.8em; color: {TEXT_DIM};
        text-transform: uppercase; letter-spacing: 1px;
    }}
    .perf-bar {{ height: 6px; border-radius: 3px; margin: 2px 0; }}
</style>
""",
    unsafe_allow_html=True,
)


# --- Sidebar: Persona picker ---
st.sidebar.markdown("## Replay Viewer")
replays = load_replay_files()

if not replays:
    st.error("No replay data found in `graph_lab/results/`.")
    st.stop()

persona = st.sidebar.selectbox("Persona", list(replays.keys()), index=0)
turns = load_turns(replays[persona])
user_id = replays[persona].stem.replace("_turns", "")

if not turns:
    st.warning(f"No turns for {persona}")
    st.stop()

total_turns = len(turns)
total_days = max(t["day"] for t in turns)
final = turns[-1]["graph_stats"]

st.sidebar.markdown(
    f"**{persona.title()}** | `{user_id}`\n\n"
    f"- {total_turns} messages over {total_days} days\n"
    f"- Final: {final.get('nodes', '?')} nodes, "
    f"{final.get('edges', '?')} edges"
)

# Scenario summary in sidebar
scenarios = [
    t["scenario_tag"] for t in turns if t.get("scenario_tag") and t["scenario_tag"] != "open_ended"
]
open_count = sum(1 for t in turns if t.get("scenario_tag") == "open_ended")
if scenarios:
    st.sidebar.markdown(f"**Scenarios:** {len(scenarios)}")
    for s in sorted(set(scenarios)):
        st.sidebar.markdown(f"- `{s}` x{scenarios.count(s)}")
if open_count:
    st.sidebar.markdown(f"- `open_ended` x{open_count}")


# --- Main: Timeline Slider ---
st.markdown(f"# {persona.title()} — Replay Timeline")

turn_idx = st.slider(
    "Message",
    min_value=1,
    max_value=total_turns,
    value=1,
    format="Turn %d",
    help="Scrub through the conversation timeline",
)

cur = turns[turn_idx - 1]

# --- Top stats row ---
cols = st.columns(6)
with cols[0]:
    st.markdown(stat_box(str(cur["day"]), "Day"), unsafe_allow_html=True)
with cols[1]:
    n_nodes = cur["graph_stats"].get("nodes", 0)
    st.markdown(stat_box(str(n_nodes), "Nodes"), unsafe_allow_html=True)
with cols[2]:
    n_edges = cur["graph_stats"].get("edges", 0)
    st.markdown(stat_box(str(n_edges), "Edges"), unsafe_allow_html=True)
with cols[3]:
    st.markdown(
        stat_box(f"{cur['total_ms']:.0f}", "Total ms"),
        unsafe_allow_html=True,
    )
with cols[4]:
    st.markdown(
        stat_box(str(turn_idx), f"of {total_turns}"),
        unsafe_allow_html=True,
    )
with cols[5]:
    prev_n = turns[turn_idx - 2]["graph_stats"].get("nodes", 0) if turn_idx > 1 else 0
    delta = n_nodes - prev_n
    d_str = f"+{delta}" if delta > 0 else str(delta)
    d_clr = ACCENT if delta > 0 else TEXT_DIM
    st.markdown(stat_box(d_str, "delta nodes", d_clr), unsafe_allow_html=True)


# --- Tags ---
tags = tag_span(f"energy: {cur['energy']}", "tag-energy")
tags += tag_span(f"mood: {cur['mood']}", "tag-mood")
tags += tag_span(cur["time_of_day"], "tag-energy")
if cur.get("scenario_tag"):
    if cur["scenario_tag"] == "open_ended":
        tags += tag_span("open_ended", "tag-open")
    else:
        tags += tag_span(cur["scenario_tag"], "tag-scenario")
st.markdown(tags, unsafe_allow_html=True)
st.markdown("")


# --- Conversation ---
left, right = st.columns([1, 1])
with left:
    st.markdown("#### User")
    st.markdown(
        f'<div class="user-msg">{cur["user_message"]}</div>',
        unsafe_allow_html=True,
    )
with right:
    st.markdown("#### Unspool")
    st.markdown(
        f'<div class="unspool-msg">{cur["unspool_response"]}</div>',
        unsafe_allow_html=True,
    )


# --- Performance breakdown ---
st.markdown("#### Performance")
perf_cols = st.columns(4)
phases = [
    ("Ingest", cur["ingest_ms"], "#E8A845"),
    ("Retrieval", cur["retrieval_ms"], "#5B8DEF"),
    ("Reasoning", cur["reasoning_ms"], ACCENT),
    ("Feedback", cur["feedback_ms"], "#9B59B6"),
]
for col, (name, ms, color) in zip(perf_cols, phases):
    total = cur["total_ms"] or 1
    pct = ms / total * 100
    col.markdown(
        f'<div style="font-size:0.8em;color:{TEXT_DIM}">{name}</div>'
        f'<div style="font-size:1.2em;font-weight:600">{ms:.0f}ms</div>'
        f'<div class="perf-bar" style="background:{BORDER};width:100%">'
        f'<div class="perf-bar" style="background:{color};'
        f'width:{pct:.0f}%"></div></div>',
        unsafe_allow_html=True,
    )


# --- Graph Visualization (on-demand to avoid lag) ---
st.markdown("---")
show_graph = st.checkbox("Show live graph (loads from DB)", value=False)

if show_graph:
    st.markdown("#### Graph State")
    with st.spinner("Loading graph from SurrealDB..."):
        all_nodes, all_edges = run_async(_query_graph(user_id))

    st.caption(
        f"{len(all_nodes)} nodes, {len(all_edges)} edges in DB"
    )

    try:
        from streamlit_agraph import Config, agraph  # noqa: E402
        from streamlit_agraph import Edge as AEdge  # noqa: E402
        from streamlit_agraph import Node as ANode  # noqa: E402

        status_set = {"not done", "done", "surfaced"}

        agraph_nodes = [
            ANode(
                id=n["id"],
                label=n.get("content", "?")[:25],
                size=8 if n.get("content", "").lower() in status_set else 18,
                color=(
                    TEXT_DIM
                    if n.get("content", "").lower() in status_set
                    else NODE_ACTIVE
                ),
                font={"color": TEXT, "size": 11},
            )
            for n in all_nodes
        ]

        agraph_edges = [
            AEdge(
                source=e.get("in", ""),
                target=e.get("out", ""),
                color=(
                    EDGE_STRONG
                    if e.get("strength", 1.0) > 0.5
                    else EDGE_WEAK
                ),
                width=max(0.5, e.get("strength", 1.0) * 3),
            )
            for e in all_edges
        ]

        config = Config(
            width=1350,
            height=550,
            directed=True,
            physics=True,
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor=ACCENT,
            collapsible=False,
            node={"highlightStrokeColor": ACCENT},
            link={"highlightColor": ACCENT},
        )

        if agraph_nodes:
            agraph(
                nodes=agraph_nodes,
                edges=agraph_edges,
                config=config,
            )
        else:
            st.info("No nodes in graph yet.")

    except ImportError:
        st.warning("Install `streamlit-agraph` for graph viz")


# --- Graph Growth Chart ---
st.markdown("#### Graph Growth")
chart_data = {
    "turn": list(range(1, total_turns + 1)),
    "nodes": [t["graph_stats"].get("nodes", 0) for t in turns],
    "edges": [t["graph_stats"].get("edges", 0) for t in turns],
}
df = pd.DataFrame(chart_data).set_index("turn")
st.line_chart(df, height=200, use_container_width=True)


# --- Conversation History (scrollable) ---
st.markdown("---")
st.markdown("#### Conversation History")

window = 5
win_start = max(0, turn_idx - window - 1)
win_end = min(total_turns, turn_idx + window)

for i in range(win_start, win_end):
    t = turns[i]
    is_cur = i == turn_idx - 1
    cls = "turn-card active" if is_cur else "turn-card"
    tag_h = ""
    if t.get("scenario_tag"):
        if t["scenario_tag"] == "open_ended":
            tag_h = tag_span("open_ended", "tag-open")
        else:
            tag_h = tag_span(t["scenario_tag"], "tag-scenario")

    u_msg = t["user_message"][:300]
    a_msg = t["unspool_response"][:300]
    gs = t["graph_stats"]
    st.markdown(
        f'<div class="{cls}">'
        f'<div style="font-size:0.75em;color:{TEXT_DIM}">'
        f"Day {t['day']} . {t['time_of_day']} . "
        f"{t['energy']} energy . {t['mood']} mood {tag_h}"
        f"</div>"
        f'<div class="user-msg" style="margin-top:8px">'
        f"<strong>User:</strong> {u_msg}</div>"
        f'<div class="unspool-msg" style="margin-top:6px">'
        f"<strong>Unspool:</strong> {a_msg}</div>"
        f'<div style="font-size:0.7em;color:{TEXT_DIM};margin-top:6px">'
        f"{t['total_ms']:.0f}ms . "
        f"nodes: {gs.get('nodes', '?')} . "
        f"edges: {gs.get('edges', '?')}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


