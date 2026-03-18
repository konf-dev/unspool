"""Typer CLI for graph_lab_sql: chat, inspect, evolve, temporal tools, replay, reset, migrate."""

import asyncio

import structlog
import typer
from graph_lab_sql.src import db
from graph_lab_sql.src.config import load_graph_config
from graph_lab_sql.src.embedding import generate_embedding
from graph_lab_sql.src.evolve import evolve_graph
from graph_lab_sql.src.feedback import apply_feedback, detect_feedback
from graph_lab_sql.src.ingest import quick_ingest
from graph_lab_sql.src.reasoning import generate_proactive, reason_and_respond_full
from graph_lab_sql.src.retrieval import build_active_subgraph
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()
app = typer.Typer(help="Graph Lab SQL — Postgres-native graph memory system")
temporal_app = typer.Typer(help="Temporal inspection commands")
app.add_typer(temporal_app, name="temporal")


@app.command()
def chat(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Interactive chat loop with graph reasoning."""
    asyncio.run(_chat_loop(user_id))


@app.command()
def inspect(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Show current graph state."""
    asyncio.run(_inspect_graph(user_id))


@app.command()
def evolve(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Run graph evolution manually."""
    asyncio.run(_run_evolution(user_id))


@app.command()
def replay(
    corpus_file: str,
    user_id: str | None = None,
    skip_feedback: bool = True,
    snapshot_interval: int = 0,
    graph_config: str | None = None,
    verbose: bool = False,
    evaluate: bool = False,
):
    """Replay a JSONL corpus through the graph pipeline."""
    from pathlib import Path

    from graph_lab_sql.corpus.replay import replay_corpus

    asyncio.run(
        replay_corpus(
            Path(corpus_file),
            user_id=user_id,
            skip_feedback=skip_feedback,
            snapshot_interval=snapshot_interval,
            graph_config=graph_config,
            verbose=verbose,
            evaluate=evaluate,
        )
    )


@app.command()
def replay_all(
    corpus_dir: str = "",
    skip_feedback: bool = True,
    verbose: bool = False,
    evaluate: bool = False,
    concurrency: int = 5,
):
    """Replay all corpus files in parallel (separate processes per persona)."""
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path

    if not corpus_dir:
        default = (
            Path(__file__).parent.parent / "graph_lab" / "corpus" / "output" / "latest"
        )
        corpus_dir = str(default)

    corpus_path = Path(corpus_dir)
    jsonl_files = sorted(corpus_path.glob("*.jsonl"))
    if not jsonl_files:
        console.print(f"[red]No .jsonl files in {corpus_dir}[/red]")
        return

    console.print(
        f"[bold]Replaying {len(jsonl_files)} corpora[/bold] "
        f"(concurrency={concurrency}, feedback={'on' if not skip_feedback else 'off'})\n"
    )

    def _run_one(path: Path) -> tuple[str, int, str]:
        cmd = [
            sys.executable,
            "-m",
            "graph_lab_sql.cli",
            "replay",
            str(path),
        ]
        if skip_feedback:
            cmd.append("--skip-feedback")
        else:
            cmd.append("--no-skip-feedback")
        if verbose:
            cmd.append("--verbose")
        if evaluate:
            cmd.append("--evaluate")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        return path.stem, result.returncode, result.stderr or result.stdout

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_run_one, f): f.stem for f in jsonl_files}
        for future in as_completed(futures):
            name = futures[future]
            try:
                persona, rc, stderr = future.result()
                if rc == 0:
                    console.print(f"  {persona}: [green]OK[/green]")
                else:
                    console.print(f"  {persona}: [red]exit {rc}[/red]")
                    if stderr:
                        for line in stderr.strip().split("\n")[-5:]:
                            console.print(f"    {line}")
            except Exception as e:
                console.print(f"  {name}: [red]Error: {e}[/red]")

    console.print("\n[bold]All replays complete.[/bold]")


@app.command()
def reset(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Clear all graph data for a user."""
    confirm = typer.confirm(f"Delete all graph data for {user_id}?")
    if confirm:
        asyncio.run(db.reset_graph(user_id))
        console.print(f"[green]Graph reset for {user_id}[/green]")


@app.command()
def migrate():
    """Create schema tables in Postgres."""
    asyncio.run(db.run_schema())
    console.print("[green]Migration complete[/green]")


@app.command()
def drop():
    """Drop all graph_lab_sql tables (dangerous)."""
    confirm = typer.confirm("This will delete ALL graph_lab_sql tables. Continue?")
    if confirm:
        asyncio.run(_drop_tables())
        console.print("[red]All tables dropped[/red]")


@app.command()
def rebuild_cache(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Rebuild the neighbor cache for a user."""
    asyncio.run(_rebuild_cache(user_id))


# --- Temporal subcommands ---


@temporal_app.command("history")
def temporal_history(
    content: str,
    user_id: str = "00000000-0000-0000-0000-000000000001",
):
    """Show edge history for a node (all versions, including invalidated)."""
    asyncio.run(_show_history(user_id, content))


@temporal_app.command("corrections")
def temporal_corrections(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Show invalidated edges (corrections/completions)."""
    asyncio.run(_show_corrections(user_id))


@temporal_app.command("stats")
def temporal_stats(user_id: str = "00000000-0000-0000-0000-000000000001"):
    """Show bi-temporal edge statistics."""
    asyncio.run(_show_temporal_stats(user_id))


# --- Async implementations ---


async def _chat_loop(user_id: str) -> None:
    console.print(f"[bold]Graph Lab SQL Chat[/bold] — user: {user_id}")
    console.print(
        "Type messages. 'quit' to exit, '/inspect' to show graph, '/evolve' to run evolution.\n"
    )

    try:
        subgraph = await build_active_subgraph(user_id, "", None, [])
        greeting = await generate_proactive(subgraph, user_id)
        if greeting:
            console.print(f"[cyan]unspool:[/cyan] {greeting}\n")
            await db.save_stream_entry(user_id, "unspool", greeting)
    except Exception as e:
        logger.debug("proactive_greeting_skipped", error=str(e))

    while True:
        try:
            message = console.input("[green]you:[/green] ")
        except (EOFError, KeyboardInterrupt):
            break

        if not message.strip():
            continue
        if message.strip().lower() == "quit":
            break
        if message.strip() == "/inspect":
            await _inspect_graph(user_id)
            continue
        if message.strip() == "/evolve":
            await _run_evolution(user_id)
            continue

        try:
            response = await _process_message(user_id, message)
            console.print(f"\n[cyan]unspool:[/cyan] {response}\n")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}\n")
            logger.error("chat_error", error=str(e), exc_info=True)

    await db.close()
    console.print("\n[dim]Session ended.[/dim]")


async def _process_message(user_id: str, message: str) -> str:
    stream_entry = await db.save_stream_entry(user_id, "user", message)
    stream_id = str(stream_entry.get("id", ""))

    quick_nodes = await quick_ingest(user_id, message, stream_id)

    try:
        message_embedding = await generate_embedding(message)
    except Exception:
        message_embedding = None

    subgraph = await build_active_subgraph(
        user_id, message, message_embedding, quick_nodes
    )
    response = await reason_and_respond_full(message, subgraph, user_id)

    await db.save_stream_entry(user_id, "unspool", response)

    config = load_graph_config()
    if not config.feedback.async_detection:
        feedback = await detect_feedback(response, subgraph, user_id)
        await apply_feedback(feedback, user_id)

    return response


async def _inspect_graph(user_id: str) -> None:
    stats = await db.get_graph_stats(user_id)
    console.print()

    table = Table(title=f"Graph Stats — {user_id}")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Nodes", str(stats.get("nodes", 0)))
    table.add_row("Current edges", str(stats.get("current_edges", 0)))
    table.add_row("Invalidated edges", str(stats.get("invalidated_edges", 0)))
    table.add_row("Total edges", str(stats.get("total_edges", 0)))
    table.add_row("Stream entries", str(stats.get("stream_entries", 0)))
    table.add_row("Cache rows", str(stats.get("cache_rows", 0)))
    console.print(table)

    recent = await db.get_recent_nodes(user_id, limit=15)
    if recent:
        node_table = Table(title="Recent Nodes")
        node_table.add_column("Content")
        node_table.add_column("ID", style="dim")
        node_table.add_column("Activated")
        for n in recent:
            node_table.add_row(
                n.get("content", ""),
                str(n.get("id", ""))[:12],
                str(n.get("last_activated_at", ""))[:19],
            )
        console.print(node_table)
    console.print()


async def _run_evolution(user_id: str) -> None:
    console.print("[yellow]Running graph evolution...[/yellow]")
    result = await evolve_graph(user_id)

    table = Table(title="Evolution Results")
    table.add_column("Action", style="bold")
    table.add_column("Count")
    table.add_row("Embeddings generated", str(result.embeddings_generated))
    table.add_row("Edges created", str(result.edges_created))
    table.add_row("Edges decayed", str(result.edges_decayed))
    table.add_row("Edges pruned (invalidated)", str(result.edges_pruned))
    table.add_row("Nodes merged", str(result.nodes_merged))
    table.add_row("Contradictions found", str(result.contradictions_found))
    console.print(table)


async def _drop_tables() -> None:
    pool = await db.get_pool()
    await pool.execute("DROP TABLE IF EXISTS node_neighbors CASCADE")
    await pool.execute("DROP TABLE IF EXISTS memory_edges CASCADE")
    await pool.execute("DROP TABLE IF EXISTS memory_nodes CASCADE")
    await pool.execute("DROP TABLE IF EXISTS raw_stream CASCADE")
    await db.close()


async def _rebuild_cache(user_id: str) -> None:
    count = await db.rebuild_neighbor_cache(user_id)
    console.print(f"[green]Rebuilt neighbor cache: {count} rows[/green]")
    await db.close()


async def _show_history(user_id: str, content: str) -> None:
    node = await db.find_node_by_content(user_id, content)
    if not node:
        console.print(f"[red]No node found with content: {content}[/red]")
        await db.close()
        return

    node_id = node["id"]
    console.print(f"\n[bold]Edge history for:[/bold] {content} ({str(node_id)[:12]})\n")

    # Get ALL edges (including invalidated)
    all_edges_from = await db.get_edges_from(node_id, current_only=False)
    all_edges_to = await db.get_edges_to(node_id, current_only=False)

    table = Table(title="Outgoing Edges")
    table.add_column("To Node")
    table.add_column("Strength")
    table.add_column("Valid From")
    table.add_column("Valid Until")
    table.add_column("Status")

    for e in all_edges_from:
        to_node = await db.get_node(e["to_node_id"])
        to_content = to_node["content"] if to_node else "?"
        status = (
            "[red]invalidated[/red]"
            if e.get("valid_until")
            else "[green]current[/green]"
        )
        table.add_row(
            to_content,
            f"{e.get('strength', 0):.2f}",
            str(e.get("valid_from", ""))[:19],
            str(e.get("valid_until", ""))[:19] if e.get("valid_until") else "—",
            status,
        )
    console.print(table)

    if all_edges_to:
        table = Table(title="Incoming Edges")
        table.add_column("From Node")
        table.add_column("Strength")
        table.add_column("Valid From")
        table.add_column("Valid Until")
        table.add_column("Status")
        for e in all_edges_to:
            from_node = await db.get_node(e["from_node_id"])
            from_content = from_node["content"] if from_node else "?"
            status = (
                "[red]invalidated[/red]"
                if e.get("valid_until")
                else "[green]current[/green]"
            )
            table.add_row(
                from_content,
                f"{e.get('strength', 0):.2f}",
                str(e.get("valid_from", ""))[:19],
                str(e.get("valid_until", ""))[:19] if e.get("valid_until") else "—",
                status,
            )
        console.print(table)

    await db.close()


async def _show_corrections(user_id: str) -> None:
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT me.*, "
        "fn.content AS from_content, tn.content AS to_content "
        "FROM memory_edges me "
        "JOIN memory_nodes fn ON fn.id = me.from_node_id "
        "JOIN memory_nodes tn ON tn.id = me.to_node_id "
        "WHERE me.user_id = $1 AND me.valid_until IS NOT NULL "
        "ORDER BY me.valid_until DESC",
        user_id,
    )

    if not rows:
        console.print("[dim]No invalidated edges found.[/dim]")
        await db.close()
        return

    table = Table(title=f"Invalidated Edges — {user_id}")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Strength")
    table.add_column("Valid From")
    table.add_column("Valid Until")
    for r in rows:
        table.add_row(
            r["from_content"],
            r["to_content"],
            f"{r['strength']:.2f}",
            str(r["valid_from"])[:19],
            str(r["valid_until"])[:19],
        )
    console.print(table)
    await db.close()


async def _show_temporal_stats(user_id: str) -> None:
    stats = await db.get_temporal_stats(user_id)
    table = Table(title=f"Temporal Stats — {user_id}")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    for k, v in stats.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)
    await db.close()


if __name__ == "__main__":
    app()
