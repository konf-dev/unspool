"""Corpus replayer — feeds JSONL through the Postgres-native graph pipeline."""

import json
import time
from pathlib import Path
from uuid import uuid4

import structlog
from graph_lab_sql.corpus.types import (
    CorpusMessage,
    DayMarker,
    ReplayEvaluation,
    ReplayResult,
    ReplayTurn,
    ScenarioScore,
)
from graph_lab_sql.src import db, llm
from graph_lab_sql.src.config import load_persona, load_simulation_config
from graph_lab_sql.src.embedding import generate_embedding
from graph_lab_sql.src.evolve import evolve_graph
from graph_lab_sql.src.feedback import apply_feedback, detect_feedback
from graph_lab_sql.src.ingest import quick_ingest
from graph_lab_sql.src.reasoning import reason_and_respond_full
from graph_lab_sql.src.retrieval import build_active_subgraph
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()

_RESULTS_DIR = Path(__file__).parent.parent / "results"


async def _graph_chat(
    user_id: str,
    message: str,
    skip_feedback: bool = False,
) -> tuple[str, dict]:
    timings: dict[str, float] = {}
    t_total = time.monotonic()

    stream_entry = await db.save_stream_entry(user_id, "user", message)
    stream_id = str(stream_entry.get("id", ""))

    t0 = time.monotonic()
    quick_nodes = await quick_ingest(user_id, message, stream_id)
    try:
        message_embedding = await generate_embedding(message)
    except Exception:
        message_embedding = None
    timings["ingest_ms"] = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    subgraph = await build_active_subgraph(
        user_id, message, message_embedding, quick_nodes
    )
    timings["retrieval_ms"] = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    response = await reason_and_respond_full(message, subgraph, user_id)
    await db.save_stream_entry(user_id, "unspool", response)
    timings["reasoning_ms"] = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    if not skip_feedback:
        try:
            feedback = await detect_feedback(response, subgraph, user_id)
            await apply_feedback(feedback, user_id)
        except Exception as e:
            logger.warning("replay_feedback_error", error=str(e))
    timings["feedback_ms"] = (time.monotonic() - t0) * 1000

    timings["total_ms"] = (time.monotonic() - t_total) * 1000
    return response, timings


async def replay_corpus(
    corpus_path: Path,
    user_id: str | None = None,
    skip_feedback: bool = True,
    snapshot_interval: int = 0,
    graph_config: str | None = None,
    verbose: bool = False,
    evaluate: bool = False,
) -> ReplayResult:
    persona = corpus_path.stem
    if user_id is None:
        user_id = str(uuid4())

    # Display name includes persona for results filenames (dashboard compat)
    display_id = f"replay-{persona}-{user_id[:8]}"

    console.print(
        f"[bold]Replaying:[/bold] {corpus_path.name} → user {display_id} ({user_id})"
    )
    if skip_feedback:
        console.print("[dim]Feedback detection: skipped[/dim]")

    result = ReplayResult(
        persona=persona,
        corpus_path=str(corpus_path),
        user_id=user_id,
        graph_config=graph_config,
    )

    _RESULTS_DIR.mkdir(exist_ok=True)
    incremental_path = _RESULTS_DIR / f"{display_id}_turns.jsonl"

    try:
        current_day = 0
        day_had_messages = False
        snapshot_counter = 0

        with open(corpus_path) as corpus_f, open(incremental_path, "w") as inc_f:
            for line in corpus_f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)

                if data.get("type") == "day_marker":
                    marker = DayMarker(**data)
                    if marker.skipped:
                        result.skipped_days += 1
                        if verbose:
                            console.print(f"  [dim]Day {marker.day}: skipped[/dim]")
                        continue

                    if current_day > 0 and day_had_messages:
                        await evolve_graph(user_id)
                        result.evolutions_run += 1

                    current_day = marker.day
                    day_had_messages = False
                    continue

                msg = CorpusMessage(**data)
                result.total_messages += 1
                day_had_messages = True

                try:
                    response, timings = await _graph_chat(
                        user_id, msg.content, skip_feedback
                    )
                except Exception as e:
                    logger.error("replay_chat_error", error=str(e), corpus_id=msg.id)
                    response = "Sorry, something went wrong."
                    timings = {}

                stats = await db.get_graph_stats(user_id)

                turn = ReplayTurn(
                    corpus_id=msg.id,
                    day=msg.day,
                    user_message=msg.content,
                    unspool_response=response,
                    ingest_ms=timings.get("ingest_ms", 0),
                    retrieval_ms=timings.get("retrieval_ms", 0),
                    reasoning_ms=timings.get("reasoning_ms", 0),
                    feedback_ms=timings.get("feedback_ms", 0),
                    total_ms=timings.get("total_ms", 0),
                    graph_stats=stats,
                    time_of_day=msg.time_of_day,
                    energy=msg.energy,
                    mood=msg.mood,
                    scenario_tag=msg.scenario_tag,
                )
                result.turns.append(turn)

                inc_f.write(turn.model_dump_json() + "\n")
                inc_f.flush()

                if verbose:
                    tag = f" [{msg.scenario_tag}]" if msg.scenario_tag else ""
                    console.print(
                        f"  [green]Day {msg.day} {msg.time_of_day}[/green]{tag} "
                        f"[{result.total_messages}/{msg.id}] "
                        f"User: {msg.content[:50]}... → "
                        f"{response[:50]}... "
                        f"[dim]({turn.total_ms:.0f}ms)[/dim]"
                    )

                snapshot_counter += 1
                if snapshot_interval > 0 and snapshot_counter % snapshot_interval == 0:
                    logger.info(
                        "replay_snapshot",
                        turn=snapshot_counter,
                        graph_stats=stats,
                    )

        # Final evolution
        if day_had_messages:
            await evolve_graph(user_id)
            result.evolutions_run += 1

        result.final_graph_stats = await db.get_graph_stats(user_id)
        result.temporal_stats = await db.get_temporal_stats(user_id)

        if evaluate:
            console.print("\n[yellow]Running evaluation...[/yellow]")
            result.evaluation = await evaluate_replay(result)
            _display_evaluation(result.evaluation)

        _save_results(result)

        console.print(
            f"\n[bold]Replay complete:[/bold] {result.total_messages} messages, "
            f"{result.evolutions_run} evolutions, "
            f"final graph: {result.final_graph_stats}"
        )
        console.print(f"[dim]Temporal: {result.temporal_stats}[/dim]")
        console.print(
            f"[dim]Graph preserved — inspect with: "
            f"python -m graph_lab_sql.cli inspect --user-id {user_id}[/dim]"
        )
    finally:
        await db.close()

    return result


async def evaluate_replay(result: ReplayResult) -> ReplayEvaluation:
    sim_config = load_simulation_config()
    eval_model = sim_config.get("evaluator", {}).get("model", "qwen2.5:7b")
    eval_temp = sim_config.get("evaluator", {}).get("temperature", 0.3)

    try:
        persona = load_persona(result.persona)
        persona_desc = f"{persona.name}, {persona.age} — {persona.background[:200]}"
    except Exception:
        persona_desc = result.persona

    transcript = _build_annotated_transcript(result.turns)

    dimensions = {
        "memory_accuracy": (
            "Did Unspool remember facts correctly across the conversation? "
            "Did it handle corrections and contradictions? Did it confuse details? "
            "The user's scenario_tags show when corrections/contradictions were "
            "intentionally injected — check if Unspool noticed. Score 1-10."
        ),
        "emotional_attunement": (
            "The [hidden] annotations show the user's actual energy and mood that "
            "Unspool could NOT see directly. Did Unspool's tone match appropriately? "
            "Did it push when the user was low-energy? Did it give space when mood "
            "was bad? Score 1-10."
        ),
        "surfacing_quality": (
            "Did Unspool surface relevant things at the right times? Did it miss "
            "deadlines or important items? Did it repeat itself? Did it prioritize "
            "well when the user mentioned many things? Score 1-10."
        ),
        "conversation_naturalness": (
            "Did Unspool feel like a natural conversation partner? Was it too "
            "robotic, too wordy, too pushy, or just right? Did it match the "
            "user's communication style? Score 1-10."
        ),
        "scenario_handling": (
            "Look at turns tagged with scenario types (contradictions, corrections, "
            "ambiguity, completions, etc). How well did Unspool handle each? "
            "Did it catch time changes? Name corrections? Completion reversals? "
            "Score 1-10."
        ),
    }

    scores = {}
    for dim_name, dim_prompt in dimensions.items():
        scores[dim_name] = await _score_dimension(
            transcript, persona_desc, dim_prompt, dim_name, eval_model, eval_temp
        )

    scenario_scores = await _score_scenarios(
        result.turns, persona_desc, eval_model, eval_temp
    )
    assessment = await _overall_assessment(
        transcript, persona_desc, scores, eval_model, eval_temp
    )

    return ReplayEvaluation(
        scores=scores,
        overall_score=sum(scores.values()) / len(scores) if scores else 0,
        assessment=assessment,
        scenario_scores=scenario_scores,
    )


async def _score_dimension(
    transcript: str,
    persona_desc: str,
    dim_prompt: str,
    dim_name: str,
    model: str,
    temperature: float,
) -> float:
    prompt = f"""You are evaluating an AI assistant (Unspool) for someone with ADHD.

Persona: {persona_desc}

IMPORTANT: Lines marked [hidden: ...] show the user's ACTUAL state that Unspool
could NOT see. Unspool only saw the raw message text. Use the hidden annotations
to judge whether Unspool correctly inferred the user's state from text alone.

Lines marked [scenario: ...] show intentionally injected edge cases.

Conversation transcript (last 3000 chars):
{transcript[-3000:]}

Evaluation dimension: {dim_name}
{dim_prompt}

Return JSON: {{"score": <number 1-10>, "reasoning": "<brief explanation>"}}"""

    try:
        raw = await llm.generate_json(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
        )
        return float(raw.get("score", 5))
    except Exception:
        return 5.0


async def _score_scenarios(
    turns: list[ReplayTurn],
    persona_desc: str,
    model: str,
    temperature: float,
) -> dict[str, ScenarioScore]:
    scenario_turns: dict[str, list[ReplayTurn]] = {}
    for t in turns:
        if t.scenario_tag and t.scenario_tag != "open_ended":
            scenario_turns.setdefault(t.scenario_tag, []).append(t)

    if not scenario_turns:
        return {}

    scores: dict[str, ScenarioScore] = {}
    for tag, tagged_turns in scenario_turns.items():
        lines = []
        for t in tagged_turns:
            lines.append(f"User [{tag}]: {t.user_message}")
            lines.append(f"Unspool: {t.unspool_response}")
            lines.append("")
        mini_transcript = "\n".join(lines)

        prompt = f"""You are evaluating how an AI assistant handled a specific scenario.

Persona: {persona_desc}
Scenario type: {tag}

Conversation excerpt:
{mini_transcript[:2000]}

Did the assistant correctly handle this {tag} scenario? Consider:
- Did it notice the change/correction/edge case?
- Did it update its understanding?
- Did it respond appropriately?

Return JSON: {{"score": <number 1-10>, "reasoning": "<brief>"}}"""

        try:
            raw = await llm.generate_json(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
            )
            scores[tag] = ScenarioScore(
                score=float(raw.get("score", 5)),
                reasoning=raw.get("reasoning", ""),
            )
        except Exception:
            scores[tag] = ScenarioScore(score=5.0, reasoning="evaluation failed")

    return scores


async def _overall_assessment(
    transcript: str,
    persona_desc: str,
    scores: dict[str, float],
    model: str,
    temperature: float,
) -> str:
    prompt = f"""You evaluated an AI assistant (Unspool) for {persona_desc}.

Scores: {json.dumps(scores, indent=2)}

Write a 2-3 sentence overall assessment. What worked well? What needs improvement?
Focus on how well the system inferred user state from raw text alone."""

    try:
        return await llm.generate(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
        )
    except Exception:
        return "Evaluation failed."


def _build_annotated_transcript(turns: list[ReplayTurn]) -> str:
    lines = []
    current_day = 0
    for t in turns:
        if t.day != current_day:
            current_day = t.day
            lines.append(f"\n--- Day {t.day} ---\n")
        tag = f" [scenario: {t.scenario_tag}]" if t.scenario_tag else ""
        lines.append(
            f"[{t.time_of_day}] [hidden: energy={t.energy}, mood={t.mood}]{tag}"
        )
        lines.append(f"User: {t.user_message}")
        lines.append(f"Unspool: {t.unspool_response}")
        lines.append("")
    return "\n".join(lines)


def _display_evaluation(evaluation: ReplayEvaluation) -> None:
    if evaluation.scores:
        table = Table(title="Replay Evaluation")
        table.add_column("Dimension", style="bold")
        table.add_column("Score")
        for dim, score in evaluation.scores.items():
            color = "green" if score >= 7 else "yellow" if score >= 5 else "red"
            table.add_row(dim, f"[{color}]{score:.1f}[/{color}]")
        table.add_row("OVERALL", f"[bold]{evaluation.overall_score:.1f}[/bold]")
        console.print(table)

    if evaluation.scenario_scores:
        table = Table(title="Scenario Scores")
        table.add_column("Scenario", style="bold")
        table.add_column("Score")
        table.add_column("Notes", style="dim")
        for tag, sc in sorted(evaluation.scenario_scores.items()):
            color = "green" if sc.score >= 7 else "yellow" if sc.score >= 5 else "red"
            table.add_row(tag, f"[{color}]{sc.score:.1f}[/{color}]", sc.reasoning[:60])
        console.print(table)

    if evaluation.assessment:
        console.print(f"\n[bold]Assessment:[/bold] {evaluation.assessment}")


def _save_results(result: ReplayResult) -> None:
    _RESULTS_DIR.mkdir(exist_ok=True)

    display_id = f"replay-{result.persona}-{result.user_id[:8]}"

    json_path = _RESULTS_DIR / f"{display_id}.json"
    json_path.write_text(result.model_dump_json(indent=2))

    md_path = _RESULTS_DIR / f"{display_id}_transcript.md"
    md_path.write_text(_format_transcript_md(result))

    console.print(f"[dim]Results: {json_path}[/dim]")
    console.print(f"[dim]Transcript: {md_path}[/dim]")


def _format_transcript_md(result: ReplayResult) -> str:
    lines = [
        f"# Replay: {result.persona}",
        f"User: {result.user_id}",
        f"Corpus: {result.corpus_path}",
        f"Messages: {result.total_messages}, Evolutions: {result.evolutions_run}",
        f"Final graph: {result.final_graph_stats}",
        f"Temporal stats: {result.temporal_stats}",
        "",
    ]

    current_day = 0
    for t in result.turns:
        if t.day != current_day:
            current_day = t.day
            lines.append(f"\n## Day {t.day}\n")

        tag = f" `{t.scenario_tag}`" if t.scenario_tag else ""
        meta = f"energy={t.energy} mood={t.mood}"
        lines.append(f"**[{t.time_of_day}]** _{meta}_{tag}")
        lines.append(f"> User: {t.user_message}")
        lines.append(f"*Unspool:* {t.unspool_response}")
        if t.total_ms > 0:
            lines.append(
                f"*perf: ingest={t.ingest_ms:.0f}ms "
                f"retrieval={t.retrieval_ms:.0f}ms "
                f"reasoning={t.reasoning_ms:.0f}ms "
                f"total={t.total_ms:.0f}ms*"
            )
        lines.append("")

    if result.evaluation.scores:
        lines.append("\n## Evaluation\n")
        for dim, score in result.evaluation.scores.items():
            lines.append(f"- **{dim}**: {score:.1f}/10")
        lines.append(f"- **OVERALL**: {result.evaluation.overall_score:.1f}/10")
        lines.append(f"\n{result.evaluation.assessment}")

        if result.evaluation.scenario_scores:
            lines.append("\n### Scenario Scores\n")
            for tag, sc in sorted(result.evaluation.scenario_scores.items()):
                lines.append(f"- **{tag}**: {sc.score:.1f}/10 — {sc.reasoning}")

    return "\n".join(lines)
