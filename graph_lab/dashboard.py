"""Streamlit dashboard for visual graph debugging."""

import asyncio

import streamlit as st

st.set_page_config(page_title="Graph Lab", layout="wide")

from graph_lab.src import db  # noqa: E402
from graph_lab.src.embedding import generate_embedding  # noqa: E402
from graph_lab.src.evolve import evolve_graph  # noqa: E402
from graph_lab.src.ingest import quick_ingest  # noqa: E402
from graph_lab.src.reasoning import reason_and_respond_full  # noqa: E402
from graph_lab.src.retrieval import build_active_subgraph  # noqa: E402


def run_async(coro):
    """Run async function in streamlit context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- Sidebar ---
st.sidebar.title("Graph Lab")
user_id = st.sidebar.text_input("User ID", value="test-user-1")
page = st.sidebar.radio("Page", ["Chat", "Graph", "Triggers", "Evolution", "Timeline"])


# --- Chat Page ---
if page == "Chat":
    st.title("Chat")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Type a message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    # Save stream entry
                    stream_entry = run_async(db.save_stream_entry(user_id, "user", prompt))
                    stream_id = stream_entry.get("id", "")

                    # Ingest
                    quick_nodes = run_async(quick_ingest(user_id, prompt, stream_id))
                    st.sidebar.write(f"Nodes extracted: {len(quick_nodes)}")

                    # Embedding
                    try:
                        emb = run_async(generate_embedding(prompt))
                    except Exception:
                        emb = None

                    # Retrieval
                    subgraph = run_async(build_active_subgraph(user_id, prompt, emb, quick_nodes))
                    st.sidebar.write(
                        f"Subgraph: {len(subgraph.nodes)} nodes, {len(subgraph.edges)} edges"
                    )

                    # Reasoning
                    response = run_async(reason_and_respond_full(prompt, subgraph, user_id))
                    run_async(db.save_stream_entry(user_id, "unspool", response))

                    st.write(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})

                except Exception as e:
                    st.error(f"Error: {e}")


# --- Graph Page ---
elif page == "Graph":
    st.title("Graph Visualization")

    stats = run_async(db.get_graph_stats(user_id))
    col1, col2, col3 = st.columns(3)
    col1.metric("Nodes", stats["nodes"])
    col2.metric("Edges", stats["edges"])
    col3.metric("Stream entries", stats["stream_entries"])

    nodes = run_async(db.get_all_nodes(user_id))
    if nodes:
        st.subheader("All Nodes")
        for n in nodes:
            nid = str(n.get("id", ""))[:12]
            activated = str(n.get("last_activated_at", ""))[:19]
            st.write(f"**{n.get('content', '')}** — {nid} — activated: {activated}")

        # Simple edge visualization
        node_ids = [n["id"] for n in nodes]
        edges = run_async(db.get_edges_between(node_ids))
        if edges:
            st.subheader("Edges")
            node_id_to_content = {n["id"]: n.get("content", "?") for n in nodes}
            for e in edges:
                from_c = node_id_to_content.get(e.get("in", ""), "?")
                to_c = node_id_to_content.get(e.get("out", ""), "?")
                strength = e.get("strength", 1.0)
                st.write(f"{from_c} → {to_c} (strength: {strength:.2f})")

        # Try streamlit-agraph if available
        try:
            from streamlit_agraph import Config, agraph
            from streamlit_agraph import Edge as AEdge
            from streamlit_agraph import Node as ANode

            agraph_nodes = [
                ANode(id=n["id"], label=n.get("content", "?")[:20], size=15) for n in nodes
            ]
            agraph_edges = [AEdge(source=e.get("in", ""), target=e.get("out", "")) for e in edges]
            config = Config(
                width=800,
                height=500,
                directed=True,
                physics=True,
                hierarchical=False,
            )
            agraph(nodes=agraph_nodes, edges=agraph_edges, config=config)
        except ImportError:
            st.info("Install streamlit-agraph for visual graph rendering.")
    else:
        st.info("No nodes yet. Send some messages in the Chat page.")


# --- Triggers Page ---
elif page == "Triggers":
    st.title("Trigger Inspector")
    st.info("Send a message in the Chat page to see trigger results in the sidebar.")

    message = st.text_input("Test message (dry run triggers)")
    if message and st.button("Run Triggers"):
        with st.spinner("Running triggers..."):
            try:
                emb = run_async(generate_embedding(message))
            except Exception:
                emb = None
            subgraph = run_async(build_active_subgraph(user_id, message, emb, []))
            for tr in subgraph.trigger_results:
                st.write(f"**{tr.trigger_name}**: {len(tr.node_ids)} nodes — {tr.metadata}")


# --- Evolution Page ---
elif page == "Evolution":
    st.title("Graph Evolution")

    if st.button("Run Evolution"):
        with st.spinner("Evolving graph..."):
            result = run_async(evolve_graph(user_id))
            st.json(result.model_dump())


# --- Timeline Page ---
elif page == "Timeline":
    st.title("Raw Stream Timeline")

    stream = run_async(db.get_recent_stream(user_id, limit=50))
    if stream:
        for entry in reversed(stream):
            source = entry.get("source", "?")
            content = entry.get("content", "")
            ts = str(entry.get("created_at", ""))[:19]
            if source == "user":
                st.markdown(f"**[{ts}] User:** {content}")
            elif source == "unspool":
                st.markdown(f"*[{ts}] Unspool:* {content}")
            else:
                st.markdown(f"[{ts}] {source}: {content}")
    else:
        st.info("No stream entries yet.")
