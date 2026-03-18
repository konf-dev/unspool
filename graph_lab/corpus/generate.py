"""Corpus generator — produces JSONL per persona without graph system."""

import asyncio
import json
import random
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
import yaml
from graph_lab.corpus.types import (
    CorpusConfig,
    CorpusMessage,
    DayMarker,
    ScenarioDef,
    ScenarioFile,
    ScheduledScenario,
)
from graph_lab.src import llm
from graph_lab.src.config import OLLAMA_URL, load_persona
from openai import AsyncOpenAI
from rich.console import Console

logger = structlog.get_logger()
console = Console()

_CORPUS_ROOT = Path(__file__).parent
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_SCENARIOS_DIR = _CORPUS_ROOT / "scenarios"
_OUTPUT_DIR = _CORPUS_ROOT / "output"

TIMES_OF_DAY = ["morning", "afternoon", "evening", "late night"]


def load_corpus_config() -> CorpusConfig:
    path = _CONFIG_DIR / "corpus.yaml"
    if not path.exists():
        return CorpusConfig()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return CorpusConfig(**raw)


def load_all_scenarios() -> list[ScenarioDef]:
    """Load all scenario definitions from the scenarios directory."""
    scenarios: list[ScenarioDef] = []
    if not _SCENARIOS_DIR.exists():
        return scenarios
    for path in sorted(_SCENARIOS_DIR.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        sf = ScenarioFile(**raw)
        scenarios.extend(sf.scenarios)
    return scenarios


def schedule_scenarios(
    scenarios: list[ScenarioDef],
    persona: str,
    total_days: int,
    rng: random.Random,
) -> list[ScheduledScenario]:
    """Distribute scenarios across the persona's timeline."""
    scheduled: list[ScheduledScenario] = []
    for scenario in scenarios:
        inject = scenario.inject_at
        day_lo, day_hi = inject.get("day_range", [1, total_days])
        day_hi = min(day_hi, total_days)
        count = inject.get("count", 1)
        for _ in range(count):
            if day_lo > day_hi:
                continue
            start_day = rng.randint(day_lo, day_hi)
            scheduled.append(
                ScheduledScenario(
                    scenario_id=scenario.id,
                    persona=persona,
                    start_day=start_day,
                    current_step=0,
                    messages_until_next=0,
                    steps=scenario.steps,
                )
            )
    return scheduled


def _get_active_injection(
    day: int,
    active_scenarios: list[ScheduledScenario],
    rng: random.Random,
) -> tuple[str | None, str | None]:
    """Check if any scenario step should fire. Returns (instruction, scenario_id)."""
    fired_instruction: str | None = None
    fired_id: str | None = None
    fired_sc: ScheduledScenario | None = None

    for sc in active_scenarios:
        if sc.current_step >= len(sc.steps):
            continue
        if day < sc.start_day:
            continue

        # Only fire the first matching scenario per message
        if fired_instruction is not None:
            continue

        step = sc.steps[sc.current_step]

        # First step fires immediately on start_day
        if sc.current_step == 0 and day >= sc.start_day and sc.messages_until_next == 0:
            sc.current_step += 1
            if sc.current_step < len(sc.steps):
                next_step = sc.steps[sc.current_step]
                delay = next_step.delay_messages
                sc.messages_until_next = (
                    rng.randint(delay[0], delay[1]) if len(delay) == 2 and delay[1] > 0 else 0
                )
            fired_instruction = step.instruction
            fired_id = sc.scenario_id
            fired_sc = sc
            continue

        # Subsequent steps count down messages
        if sc.current_step > 0 and sc.messages_until_next <= 0:
            sc.current_step += 1
            if sc.current_step < len(sc.steps):
                next_step = sc.steps[sc.current_step]
                delay = next_step.delay_messages
                sc.messages_until_next = (
                    rng.randint(delay[0], delay[1]) if len(delay) == 2 and delay[1] > 0 else 0
                )
            fired_instruction = step.instruction
            fired_id = sc.scenario_id
            fired_sc = sc
            continue

    # Decrement counters for all waiting scenarios (except the one that just fired)
    for sc in active_scenarios:
        if sc is fired_sc:
            continue
        if sc.messages_until_next > 0:
            sc.messages_until_next -= 1

    return fired_instruction, fired_id


LLMGenerateFn = Callable[..., Coroutine[Any, Any, str]]


def _make_llm_fn(model: str, ollama_url: str | None) -> LLMGenerateFn:
    """Create an LLM generate function, optionally with a custom Ollama URL."""
    provider = llm._route(model)

    if provider == "ollama" and ollama_url and ollama_url != OLLAMA_URL:
        # Custom Ollama instance — create a dedicated client
        client = AsyncOpenAI(base_url=f"{ollama_url}/v1", api_key="ollama")
        default_model = model

        async def _generate(
            messages: list[dict],
            model: str | None = None,
            temperature: float = 0.7,
            max_tokens: int = 4096,
            **kwargs: Any,
        ) -> str:
            msgs = llm._build_openai_messages(messages, kwargs.get("system"))
            response = await client.chat.completions.create(
                model=model or default_model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""

        return _generate

    # Default: use the shared llm.generate
    return llm.generate


def _build_persona_summary(persona_dict: dict) -> str:
    """Compact persona summary — name, age, background, personality, patterns."""
    name = persona_dict.get("name", "User")
    age = persona_dict.get("age", "")
    bg = persona_dict.get("background", "")
    personality = yaml.dump(persona_dict.get("personality", {}), default_flow_style=False)
    patterns = "\n".join(f"- {p}" for p in persona_dict.get("behavior_patterns", []))
    current = yaml.dump(persona_dict.get("current_life", {}), default_flow_style=False)
    return (
        f"Name: {name}, Age: {age}\n"
        f"Background: {bg}\n"
        f"Personality:\n{personality}\n"
        f"Current life:\n{current}\n"
        f"Behavior patterns:\n{patterns}"
    )


def _dedup_history(history: list[str], limit: int = 10) -> list[str]:
    """Return recent unique messages, keeping order. Prevents LLM echo loops."""
    seen: set[str] = set()
    unique: list[str] = []
    for msg in reversed(history):
        normalized = msg.strip().lower()[:80]
        if normalized not in seen:
            seen.add(normalized)
            unique.append(msg)
            if len(unique) >= limit:
                break
    unique.reverse()
    return unique


async def generate_message(
    persona_dict: dict,
    history: list[str],
    state: dict,
    model: str,
    temperature: float,
    scenario_instruction: str | None = None,
    open_ended: bool = False,
    llm_fn: LLMGenerateFn | None = None,
) -> str | None:
    """Generate a single user message. Adapted from UserSimulator.generate_message."""
    gen = llm_fn or llm.generate
    recent = _dedup_history(history, limit=10)
    recent_text = "\n".join(f"  [{i + 1}] {m}" for i, m in enumerate(recent))
    persona_summary = _build_persona_summary(persona_dict)

    anti_repeat = ""
    if recent:
        anti_repeat = (
            "\nCRITICAL: Do NOT repeat or paraphrase your recent messages above. "
            "Each message must be about something DIFFERENT — a new topic, a new task, "
            "a new feeling, or a new update. Vary your opening words and sentence structure.\n"
        )

    if open_ended:
        prompt = f"""You are simulating a real person with ADHD using a chat app. Stay in character.

{persona_summary}

Day {state["day"]}, {state["time_of_day"]}. Energy: {state["energy"]}. Mood: {state["mood"]}.

Your recent messages (DO NOT repeat these):
{recent_text}
{anti_repeat}
Send your next message to the app. Be completely natural — say whatever this person
would actually type right now. No format constraints. Could be anything: a task, a vent,
a random thought, a question, silence (SKIP), a follow-up, something new entirely.

Return ONLY the message text, or SKIP."""
    else:
        injection = ""
        if scenario_instruction:
            injection = f"\nIMPORTANT: In this message, you MUST {scenario_instruction}\n"

        prompt = f"""You are simulating a user with ADHD. Stay in character.

{persona_summary}

Current state:
- Day {state["day"]} of simulation
- Energy: {state["energy"]}
- Mood: {state["mood"]}
- Time of day: {state["time_of_day"]}
{injection}
Your recent messages (DO NOT repeat these):
{recent_text}
{anti_repeat}
Generate the user's next message. Be realistic:
- ADHD brain dumps are messy, not organized
- Sometimes they just say "hey" or "what should I do"
- Sometimes they report completions, vent, or mention new things
- Their energy and mood affect what they say and how
- No Unspool response context — you're just dumping thoughts
- VARY your message: different topic, different length, different tone each time

Return ONLY the message text, or SKIP if the user wouldn't message right now."""

    response = await gen(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=temperature,
    )
    text = response.strip()
    if text.upper() == "SKIP":
        return None
    # Strip wrapping quotes the LLM sometimes adds
    if len(text) > 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text


def _is_repetitive(content: str, history: list[str], threshold: float = 0.7) -> bool:
    """Check if content is too similar to recent history (simple word overlap)."""
    if not history:
        return False
    content_words = set(content.lower().split())
    if not content_words:
        return False
    for prev in history[-3:]:
        prev_words = set(prev.lower().split())
        if not prev_words:
            continue
        overlap = len(content_words & prev_words) / max(len(content_words), len(prev_words))
        if overlap > threshold:
            return True
    return False


async def _generate_with_retry(
    persona_dict: dict,
    history: list[str],
    state: dict,
    model: str,
    temperature: float,
    injection: str | None,
    open_ended: bool,
    max_retries: int,
    persona_name: str,
    llm_fn: LLMGenerateFn | None = None,
) -> tuple[str | None, str]:
    """Generate with retries on failure or repetition. Returns (content, model_used)."""
    for attempt in range(max_retries + 1):
        try:
            content = await generate_message(
                persona_dict, history, state, model, temperature, injection, open_ended, llm_fn
            )
            if content and _is_repetitive(content, history):
                if attempt < max_retries:
                    logger.debug("repetition_detected", persona=persona_name, attempt=attempt + 1)
                    continue
                # Last attempt — accept it anyway, validator will flag it
            return content, model
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "generation_retry",
                    persona=persona_name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(1)
            else:
                logger.error(
                    "generation_failed",
                    persona=persona_name,
                    day=state["day"],
                    error=str(e),
                )
                return None, model


async def generate_persona_corpus(
    persona_name: str,
    days: int,
    config: CorpusConfig,
    scenarios: list[ScenarioDef],
    output_dir: Path,
    seed: int | None = None,
    verbose: bool = False,
) -> Path:
    """Generate JSONL corpus for one persona."""
    rng = random.Random(seed)
    persona = load_persona(persona_name)
    persona_dict = persona.model_dump()

    model = config.persona_models.get(persona_name, config.default_model)
    hardcoded = config.hardcoded_messages.get(persona_name, [])
    open_ended_ratio = config.open_ended.get(persona_name, 0.0)
    ollama_url = config.persona_ollama_urls.get(persona_name)
    llm_fn = _make_llm_fn(model, ollama_url)

    # Schedule scenarios for this persona
    scheduled = schedule_scenarios(scenarios, persona_name, days, rng)

    output_path = output_dir / f"{persona_name}.jsonl"
    history: list[str] = []
    msg_global_count = 0
    errors = 0

    sim_days = min(days, persona.simulation.duration_days)

    with open(output_path, "w") as f:
        for day in range(1, sim_days + 1):
            # Determine day state
            if rng.random() < persona.simulation.bad_day_probability:
                energy, mood = "low", "bad"
            elif rng.random() < 0.3:
                energy, mood = "high", "good"
            else:
                energy, mood = "medium", "neutral"

            # Skip day?
            if rng.random() < persona.simulation.skip_day_probability:
                marker = DayMarker(
                    id=f"{persona_name}-d{day:03d}-skip",
                    persona=persona_name,
                    day=day,
                    skipped=True,
                )
                f.write(marker.model_dump_json() + "\n")
                if verbose:
                    console.print(f"  [dim]Day {day}: skipped[/dim]")
                continue

            # Day marker
            marker = DayMarker(
                id=f"{persona_name}-d{day:03d}-start",
                persona=persona_name,
                day=day,
                skipped=False,
            )
            f.write(marker.model_dump_json() + "\n")

            min_msgs, max_msgs = persona.simulation.messages_per_day
            num_messages = rng.randint(min_msgs, max_msgs)

            for msg_idx in range(num_messages):
                time_of_day = rng.choice(TIMES_OF_DAY)
                state = {
                    "day": day,
                    "energy": energy,
                    "mood": mood,
                    "time_of_day": time_of_day,
                }

                # Check for scenario injection
                injection, scenario_tag = _get_active_injection(day, scheduled, rng)

                # Decide generation mode
                use_open_ended = (
                    not injection and open_ended_ratio > 0 and rng.random() < open_ended_ratio
                )

                # Chance of hardcoded message (15% for personas that have them)
                if hardcoded and rng.random() < 0.15 and not injection and not use_open_ended:
                    content = rng.choice(hardcoded)
                    gen_model = "hardcoded"
                else:
                    content, gen_model = await _generate_with_retry(
                        persona_dict,
                        history,
                        state,
                        model,
                        config.temperature,
                        injection,
                        use_open_ended,
                        config.max_retries,
                        persona_name,
                        llm_fn,
                    )
                    if content is None:
                        errors += 1
                        continue

                if use_open_ended:
                    scenario_tag = "open_ended"

                msg = CorpusMessage(
                    id=f"{persona_name}-d{day:03d}-m{msg_idx:03d}",
                    persona=persona_name,
                    day=day,
                    message_index=msg_idx,
                    time_of_day=time_of_day,
                    energy=energy,
                    mood=mood,
                    content=content,
                    scenario_tag=scenario_tag,
                    generation_model=gen_model,
                )
                f.write(msg.model_dump_json() + "\n")
                history.append(content)
                msg_global_count += 1

            if verbose:
                console.print(
                    f"  [green]Day {day}[/green]: {num_messages} messages, "
                    f"energy={energy}, mood={mood}"
                )

    error_note = f" ({errors} errors)" if errors else ""
    console.print(
        f"[bold]{persona_name}[/bold]: {msg_global_count} messages → {output_path.name}{error_note}"
    )
    return output_path


async def generate_corpus(
    days: int | None = None,
    personas: list[str] | None = None,
    seed: int | None = None,
    verbose: bool = False,
) -> Path:
    """Generate corpus for all (or specified) personas."""
    config = load_corpus_config()
    scenarios = load_all_scenarios()
    gen_days = days or config.default_days

    if personas is None:
        persona_dir = _CONFIG_DIR / "personas"
        personas = [p.stem for p in sorted(persona_dir.glob("*.yaml"))]

    # Create timestamped output dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _OUTPUT_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # Maintain a "latest" symlink
    latest_link = _OUTPUT_DIR / "latest"
    if latest_link.is_symlink():
        latest_link.unlink()
    elif latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(timestamp)

    open_personas = [p for p in personas if config.open_ended.get(p, 0) > 0]
    console.print(f"[bold]Generating corpus[/bold]: {len(personas)} personas × {gen_days} days")
    console.print(f"Scenarios loaded: {len(scenarios)}")
    if open_personas:
        console.print(
            f"Open-ended personas: {', '.join(open_personas)} "
            f"({', '.join(f'{config.open_ended[p]:.0%}' for p in open_personas)})"
        )
    console.print(f"Output: {output_dir}\n")

    # Run personas with bounded concurrency
    sem = asyncio.Semaphore(config.concurrency)

    async def _worker(name: str, idx: int) -> Path:
        async with sem:
            persona_seed = seed + idx if seed is not None else None
            return await generate_persona_corpus(
                name, gen_days, config, scenarios, output_dir, persona_seed, verbose
            )

    tasks = [_worker(name, i) for i, name in enumerate(personas)]
    paths = await asyncio.gather(*tasks, return_exceptions=True)

    # Report
    successes = [p for p in paths if isinstance(p, Path)]
    failures = [p for p in paths if isinstance(p, Exception)]
    console.print(f"\n[bold]Done:[/bold] {len(successes)} succeeded, {len(failures)} failed")
    for exc in failures:
        console.print(f"  [red]Error:[/red] {exc}")

    # Save generation metadata
    meta = {
        "timestamp": timestamp,
        "days": gen_days,
        "personas": personas,
        "scenarios_count": len(scenarios),
        "seed": seed,
        "config": config.model_dump(),
    }
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    return output_dir
