"""Typer CLI for graph lab: chat, inspect, evolve, simulate, reset, migrate."""

import asyncio

import structlog
import typer
from graph_lab.migrate import drop_all, run_migration
from graph_lab.src import db
from graph_lab.src.config import load_graph_config
from graph_lab.src.embedding import generate_embedding
from graph_lab.src.evolve import evolve_graph
from graph_lab.src.feedback import apply_feedback, detect_feedback
from graph_lab.src.ingest import quick_ingest
from graph_lab.src.reasoning import generate_proactive, reason_and_respond_full
from graph_lab.src.retrieval import build_active_subgraph
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()
app = typer.Typer(help="Graph Lab — experimental graph memory system")


@app.command()
def chat(user_id: str = "test-user-1"):
    """Interactive chat loop with graph reasoning."""
    asyncio.run(_chat_loop(user_id))


@app.command()
def inspect(user_id: str = "test-user-1"):
    """Show current graph state."""
    asyncio.run(_inspect_graph(user_id))


@app.command()
def evolve(user_id: str = "test-user-1"):
    """Run graph evolution manually."""
    asyncio.run(_run_evolution(user_id))


@app.command()
def simulate(
    persona: str = "maya",
    days: int = 30,
    seed: int | None = None,
    verbose: bool = False,
):
    """Run a full simulation with LLM-powered user + evaluator."""
    from graph_lab.simulate import run_simulation

    asyncio.run(run_simulation(persona, days, seed, verbose))


@app.command()
def batch(
    personas: str = "maya,marcus,priya",
    days: int = 30,
    runs: int = 3,
    verbose: bool = False,
):
    """Run batch simulations across personas. Resumable on crash."""
    from graph_lab.batch import run_batch

    persona_list = [p.strip() for p in personas.split(",")]
    asyncio.run(run_batch(persona_list, days, runs, verbose=verbose))


@app.command()
def generate_corpus(
    days: int | None = None,
    personas: str | None = None,
    seed: int | None = None,
    verbose: bool = False,
):
    """Generate JSONL corpus for personas (no graph system involved)."""
    from graph_lab.corpus.generate import generate_corpus as _generate

    persona_list = [p.strip() for p in personas.split(",")] if personas else None
    asyncio.run(_generate(days, persona_list, seed, verbose))


@app.command()
def validate_corpus(corpus_dir: str):
    """Validate generated corpus files."""
    from pathlib import Path

    from graph_lab.corpus.validate import validate_corpus_dir

    validate_corpus_dir(Path(corpus_dir))


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

    from graph_lab.corpus.replay import replay_corpus

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
        default = Path(__file__).parent / "corpus" / "output" / "latest"
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
            "graph_lab.cli",
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
def reset(user_id: str = "test-user-1"):
    """Clear all graph data for a user."""
    confirm = typer.confirm(f"Delete all graph data for {user_id}?")
    if confirm:
        asyncio.run(db.reset_graph(user_id))
        console.print(f"[green]Graph reset for {user_id}[/green]")


@app.command()
def migrate():
    """Create graph_lab schema and tables in SurrealDB."""
    asyncio.run(run_migration())
    console.print("[green]Migration complete[/green]")


@app.command()
def drop():
    """Drop all graph_lab data (dangerous)."""
    confirm = typer.confirm("This will delete ALL graph_lab data. Continue?")
    if confirm:
        asyncio.run(drop_all())
        console.print("[red]All data dropped[/red]")


async def _chat_loop(user_id: str) -> None:
    console.print(f"[bold]Graph Lab Chat[/bold] — user: {user_id}")
    console.print(
        "Type messages. 'quit' to exit, '/inspect' to show graph, '/evolve' to run evolution.\n"
    )

    # Proactive greeting on session start
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
    """Full pipeline: ingest → triggers → retrieval → reasoning → feedback."""
    # Save to raw stream
    stream_entry = await db.save_stream_entry(user_id, "user", message)
    stream_id = stream_entry.get("id", "")

    # Quick ingest: extract nodes
    quick_nodes = await quick_ingest(user_id, message, stream_id)

    # Generate embedding for message
    try:
        message_embedding = await generate_embedding(message)
    except Exception:
        message_embedding = None

    # Build active subgraph via trigger chain
    subgraph = await build_active_subgraph(user_id, message, message_embedding, quick_nodes)

    # Reason and respond
    response = await reason_and_respond_full(message, subgraph, user_id)

    # Save response to stream
    await db.save_stream_entry(user_id, "unspool", response)

    # Async feedback detection
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
    table.add_row("Nodes", str(stats["nodes"]))
    table.add_row("Edges", str(stats["edges"]))
    table.add_row("Stream entries", str(stats["stream_entries"]))
    console.print(table)

    # Show recent nodes
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
    table.add_row("Edges pruned", str(result.edges_pruned))
    table.add_row("Nodes merged", str(result.nodes_merged))
    table.add_row("Contradictions found", str(result.contradictions_found))
    console.print(table)


if __name__ == "__main__":
    app()
