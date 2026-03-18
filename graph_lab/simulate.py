"""Simulation engine: user LLM + graph system + evaluator LLM."""

import json
import random
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import structlog
import yaml
from graph_lab.src import db, llm
from graph_lab.src.config import load_persona, load_simulation_config
from graph_lab.src.embedding import generate_embedding
from graph_lab.src.evolve import evolve_graph
from graph_lab.src.feedback import apply_feedback, detect_feedback
from graph_lab.src.ingest import quick_ingest
from graph_lab.src.reasoning import reason_and_respond_full
from graph_lab.src.retrieval import build_active_subgraph
from graph_lab.src.types import EvaluationResult, SimulationResult, SimulationTurn, TurnPerf
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger()
console = Console()


class UserSimulator:
    """LLM-powered user that plays a persona realistically."""

    def __init__(self, persona: dict, model: str, temperature: float = 0.9):
        self.persona = persona
        self.model = model
        self.temperature = temperature
        self.internal_state = {
            "day": 1,
            "energy": "medium",
            "mood": "neutral",
            "things_remembered": [],
            "things_forgot": [],
        }
        self.conversation_history: list[dict] = []

    async def generate_message(self, unspool_last_said: str | None, context: dict) -> str | None:
        """Generate next user message. Returns None if user wouldn't message."""
        recent = self.conversation_history[-6:] if self.conversation_history else []
        recent_text = "\n".join(f"  {t['role']}: {t['content']}" for t in recent)

        prompt = f"""You are simulating a user with ADHD. Stay in character.

Persona: {yaml.dump(self.persona, default_flow_style=False)}

Current state:
- Day {self.internal_state["day"]} of simulation
- Energy: {self.internal_state["energy"]}
- Mood: {self.internal_state["mood"]}
- Time of day: {context.get("time_of_day", "evening")}

What the app last said: {unspool_last_said or "(first message, or app just opened)"}

Recent conversation:
{recent_text}

Generate the user's next message. Be realistic:
- ADHD brain dumps are messy, not organized
- Sometimes they just say "hey" or "what should I do"
- Sometimes they report completions
- Sometimes they vent
- Sometimes they mention new things mid-conversation
- Their energy and mood affect what they say and how

Return ONLY the message text, or SKIP if the user wouldn't message right now."""

        response = await llm.generate(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            temperature=self.temperature,
        )
        text = response.strip()
        if text == "SKIP":
            return None
        return text

    async def react_to_response(self, unspool_response: str) -> dict:
        """Update internal state based on Unspool's response."""
        name = self.persona.get("name", "User")
        prompt = (
            f"Given this persona and the app's response, "
            f"describe the user's reaction briefly.\n\n"
            f"Persona: {name}\n"
            f"App said: {unspool_response}\n\n"
            f"Return JSON:\n"
            f'{{"emotional_reaction": "brief description", '
            f'"energy_change": "up/down/same", '
            f'"will_respond": true}}'
        )

        try:
            raw = await llm.generate_json(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.5,
            )
            energy = raw.get("energy_change", "same")
            if energy == "up" and self.internal_state["energy"] == "low":
                self.internal_state["energy"] = "medium"
            elif energy == "up" and self.internal_state["energy"] == "medium":
                self.internal_state["energy"] = "high"
            elif energy == "down" and self.internal_state["energy"] == "high":
                self.internal_state["energy"] = "medium"
            elif energy == "down" and self.internal_state["energy"] == "medium":
                self.internal_state["energy"] = "low"
            return raw
        except Exception:
            return {"emotional_reaction": "neutral", "energy_change": "same", "will_respond": False}


class Evaluator:
    """Scores simulation quality using a separate LLM."""

    def __init__(self, model: str, temperature: float = 0.3):
        self.model = model
        self.temperature = temperature

    async def evaluate(
        self, turns: list[SimulationTurn], user_id: str, persona: dict
    ) -> EvaluationResult:
        transcript = self._format_transcript(turns)

        dimensions = {
            "surfacing_quality": (
                "Did the app surface the right things at the right times? "
                "Did it miss important deadlines? Did it repeat itself? Score 1-10."
            ),
            "emotional_intelligence": (
                "Did the app detect emotional states correctly? Did it push when "
                "it should have listened? Did it give permission to rest when needed? Score 1-10."
            ),
            "memory_accuracy": (
                "Did the app remember facts correctly? Did it handle corrections? "
                "Did it confuse details? Score 1-10."
            ),
            "strategy_adaptation": (
                "Did the app learn what works for this user? Did it adapt its "
                "approach based on what succeeded/failed? Score 1-10."
            ),
            "conversation_naturalness": (
                "Did the app feel like a natural conversation partner? Was it "
                "too robotic, too wordy, too pushy, or just right? Score 1-10."
            ),
            "graph_quality": (
                "Given the conversation, does the graph seem to capture key facts "
                "and relationships? Score 1-10 based on the graph stats and conversation flow."
            ),
        }

        scores = {}
        for dim_name, dim_prompt in dimensions.items():
            score = await self._score_dimension(transcript, persona, dim_prompt, dim_name)
            scores[dim_name] = score

        overall = await self._overall_assessment(transcript, persona, scores)

        return EvaluationResult(
            scores=scores,
            overall_score=sum(scores.values()) / len(scores) if scores else 0,
            assessment=overall,
        )

    async def _score_dimension(
        self, transcript: str, persona: dict, dim_prompt: str, dim_name: str
    ) -> float:
        prompt = f"""You are evaluating an AI assistant for someone with ADHD.

Persona: {persona.get("name", "User")} — {persona.get("background", "")[:200]}

Conversation transcript:
{transcript[:3000]}

Evaluation dimension: {dim_name}
{dim_prompt}

Return JSON: {{"score": <number 1-10>, "reasoning": "<brief explanation>"}}"""

        try:
            raw = await llm.generate_json(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=self.temperature,
            )
            return float(raw.get("score", 5))
        except Exception:
            return 5.0

    async def _overall_assessment(self, transcript: str, persona: dict, scores: dict) -> str:
        prompt = f"""You evaluated an AI assistant for {persona.get("name", "a user")} with ADHD.

Scores: {json.dumps(scores, indent=2)}

Write a 2-3 sentence overall assessment. What worked well? What needs improvement?"""

        try:
            return await llm.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=self.temperature,
            )
        except Exception:
            return "Evaluation failed."

    def _format_transcript(self, turns: list[SimulationTurn]) -> str:
        lines = []
        for t in turns:
            lines.append(f"[Day {t.day}, {t.time_of_day}]")
            lines.append(f"User: {t.user_message}")
            lines.append(f"Unspool: {t.unspool_response}")
            lines.append("")
        return "\n".join(lines)


async def run_simulation(
    persona_name: str,
    days: int = 30,
    seed: int | None = None,
    verbose: bool = False,
) -> SimulationResult:
    """Run a full simulation."""
    if seed is not None:
        random.seed(seed)

    sim_config = load_simulation_config()
    persona = load_persona(persona_name)

    sim_user_id = f"sim-{persona_name}-{uuid4().hex[:8]}"
    console.print(f"[bold]Simulation: {persona.name}[/bold] — user: {sim_user_id}")
    console.print(f"Duration: {days} days\n")

    user_sim = UserSimulator(
        persona=persona.model_dump(),
        model=sim_config["simulator"]["model"],
        temperature=sim_config["simulator"]["temperature"],
    )

    all_turns: list[SimulationTurn] = []
    sim_days = min(days, persona.simulation.duration_days)

    times_of_day = ["morning", "afternoon", "evening", "late night"]

    for day in range(1, sim_days + 1):
        user_sim.internal_state["day"] = day

        # Determine day type
        if random.random() < persona.simulation.bad_day_probability:
            user_sim.internal_state["energy"] = "low"
            user_sim.internal_state["mood"] = "bad"
        elif random.random() < 0.3:
            user_sim.internal_state["energy"] = "high"
            user_sim.internal_state["mood"] = "good"
        else:
            user_sim.internal_state["energy"] = "medium"
            user_sim.internal_state["mood"] = "neutral"

        # Skip day?
        if random.random() < persona.simulation.skip_day_probability:
            if verbose:
                console.print(f"[dim]Day {day}: skipped[/dim]")
            continue

        min_msgs, max_msgs = persona.simulation.messages_per_day
        num_messages = random.randint(min_msgs, max_msgs)

        for msg_idx in range(num_messages):
            time_of_day = random.choice(times_of_day)
            context = {"time_of_day": time_of_day, "day": day}

            # User generates message
            last_unspool = all_turns[-1].unspool_response if all_turns else None
            user_message = await user_sim.generate_message(last_unspool, context)

            if user_message is None:
                continue

            if verbose:
                console.print(
                    f"[green]Day {day} {time_of_day}[/green] User: {user_message[:80]}..."
                )

            # Graph system processes
            turn_perf = TurnPerf()
            try:
                response, turn_perf = await _graph_chat(sim_user_id, user_message)
            except Exception as e:
                logger.error("simulation_chat_error", error=str(e))
                response = "Sorry, something went wrong."

            if verbose:
                console.print(
                    f"  [cyan]Unspool:[/cyan] {response[:80]}... "
                    f"[dim]({turn_perf.total_ms:.0f}ms)[/dim]"
                )

            # User reacts
            t0 = time.monotonic()
            await user_sim.react_to_response(response)
            turn_perf.user_sim_ms = (time.monotonic() - t0) * 1000

            # Record conversation history
            user_sim.conversation_history.append({"role": "user", "content": user_message})
            user_sim.conversation_history.append({"role": "assistant", "content": response})

            # Log turn
            stats = await db.get_graph_stats(sim_user_id)
            all_turns.append(
                SimulationTurn(
                    day=day,
                    time_of_day=time_of_day,
                    user_message=user_message,
                    unspool_response=response,
                    user_state=deepcopy(user_sim.internal_state),
                    graph_stats=stats,
                    perf=turn_perf,
                )
            )

        # Run evolution at end of day
        await evolve_graph(sim_user_id)
        if verbose:
            stats = await db.get_graph_stats(sim_user_id)
            console.print(
                f"[dim]Day {day} end — nodes: {stats['nodes']}, edges: {stats['edges']}[/dim]"
            )

    # Evaluate
    console.print("\n[yellow]Running evaluation...[/yellow]")
    evaluator = Evaluator(
        model=sim_config["evaluator"]["model"],
        temperature=sim_config["evaluator"]["temperature"],
    )
    evaluation = await evaluator.evaluate(all_turns, sim_user_id, persona.model_dump())

    final_stats = await db.get_graph_stats(sim_user_id)
    result = SimulationResult(
        persona=persona_name,
        turns=all_turns,
        evaluation=evaluation,
        final_graph_stats=final_stats,
    )

    # Display results
    _display_results(result)

    # Save results — always to graph_lab/results/
    graph_lab_root = Path(__file__).parent
    output_dir = graph_lab_root / sim_config.get("output", {}).get("output_dir", "results")
    output_dir.mkdir(exist_ok=True)

    # Save full JSON (transcript + eval + graph stats per turn)
    output_path = output_dir / f"{sim_user_id}.json"
    output_path.write_text(result.model_dump_json(indent=2))

    # Save human-readable transcript
    transcript_path = output_dir / f"{sim_user_id}_transcript.md"
    transcript_path.write_text(_format_transcript_md(result))

    console.print(f"\n[dim]Results: {output_path}[/dim]")
    console.print(f"[dim]Transcript: {transcript_path}[/dim]")
    console.print(
        f"[dim]Graph preserved in SurrealDB — inspect with: "
        f"python -m graph_lab.cli inspect --user-id {sim_user_id}[/dim]"
    )

    await db.close()
    return result


async def _graph_chat(user_id: str, message: str) -> tuple[str, TurnPerf]:
    """Process a single message through the full graph pipeline. Returns (response, perf)."""
    perf = TurnPerf()
    t_total = time.monotonic()

    stream_entry = await db.save_stream_entry(user_id, "user", message)
    stream_id = stream_entry.get("id", "")

    t0 = time.monotonic()
    quick_nodes = await quick_ingest(user_id, message, stream_id)
    try:
        message_embedding = await generate_embedding(message)
    except Exception:
        message_embedding = None
    perf.ingest_ms = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    subgraph = await build_active_subgraph(user_id, message, message_embedding, quick_nodes)
    perf.retrieval_ms = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    response = await reason_and_respond_full(message, subgraph, user_id)
    await db.save_stream_entry(user_id, "unspool", response)
    perf.reasoning_ms = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    try:
        feedback = await detect_feedback(response, subgraph, user_id)
        await apply_feedback(feedback, user_id)
    except Exception as e:
        logger.warning("feedback_error", error=str(e))
    perf.feedback_ms = (time.monotonic() - t0) * 1000

    perf.total_ms = (time.monotonic() - t_total) * 1000
    return response, perf


def _display_results(result: SimulationResult) -> None:
    console.print(f"\n[bold]Simulation Complete: {result.persona}[/bold]")
    console.print(f"Turns: {len(result.turns)}")
    console.print(f"Final graph: {result.final_graph_stats}")

    # Performance stats
    if result.turns:
        perfs = [t.perf for t in result.turns]
        totals = [p.total_ms for p in perfs if p.total_ms > 0]
        if totals:
            perf_table = Table(title="Performance (ms)")
            perf_table.add_column("Phase", style="bold")
            perf_table.add_column("Avg")
            perf_table.add_column("Min")
            perf_table.add_column("Max")
            for phase in ["ingest_ms", "retrieval_ms", "reasoning_ms", "feedback_ms", "total_ms"]:
                vals = [getattr(p, phase) for p in perfs if getattr(p, phase) > 0]
                if vals:
                    label = phase.replace("_ms", "")
                    perf_table.add_row(
                        label,
                        f"{sum(vals) / len(vals):.0f}",
                        f"{min(vals):.0f}",
                        f"{max(vals):.0f}",
                    )
            console.print(perf_table)

    if result.evaluation.scores:
        table = Table(title="Evaluation Scores")
        table.add_column("Dimension", style="bold")
        table.add_column("Score")
        for dim, score in result.evaluation.scores.items():
            color = "green" if score >= 7 else "yellow" if score >= 5 else "red"
            table.add_row(dim, f"[{color}]{score:.1f}[/{color}]")
        table.add_row("OVERALL", f"[bold]{result.evaluation.overall_score:.1f}[/bold]")
        console.print(table)

    if result.evaluation.assessment:
        console.print(f"\n[bold]Assessment:[/bold] {result.evaluation.assessment}")


def _format_transcript_md(result: SimulationResult) -> str:
    """Format simulation as a human-readable markdown transcript."""
    lines = [
        f"# Simulation: {result.persona}",
        f"Turns: {len(result.turns)}",
        f"Final graph: {result.final_graph_stats}",
        "",
    ]

    current_day = 0
    for t in result.turns:
        if t.day != current_day:
            current_day = t.day
            lines.append(f"\n## Day {t.day}\n")
        lines.append(f"**[{t.time_of_day}]** User: {t.user_message}")
        lines.append(f"*Unspool:* {t.unspool_response}")
        if t.perf.total_ms > 0:
            lines.append(
                f"*perf: ingest={t.perf.ingest_ms:.0f}ms "
                f"retrieval={t.perf.retrieval_ms:.0f}ms "
                f"reasoning={t.perf.reasoning_ms:.0f}ms "
                f"total={t.perf.total_ms:.0f}ms*"
            )
        lines.append(f"*graph: {t.graph_stats}*")
        lines.append("")

    if result.evaluation.scores:
        lines.append("\n## Evaluation\n")
        for dim, score in result.evaluation.scores.items():
            lines.append(f"- **{dim}**: {score:.1f}/10")
        lines.append(f"- **OVERALL**: {result.evaluation.overall_score:.1f}/10")
        lines.append(f"\n{result.evaluation.assessment}")

    return "\n".join(lines)
