"""LLM reasoning + response generation using graph context."""

from collections.abc import AsyncIterator

import structlog
from graph_lab.src import db, llm
from graph_lab.src.config import load_graph_config, load_prompt, resolve_model
from graph_lab.src.serialization import serialize_subgraph
from graph_lab.src.types import ActiveSubgraph
from jinja2 import Template

logger = structlog.get_logger()


async def reason_and_respond(
    user_message: str,
    subgraph: ActiveSubgraph,
    user_id: str,
) -> AsyncIterator[str]:
    """Single LLM call with full subgraph context. Streams response."""
    config = load_graph_config()
    model = resolve_model(config.reasoning.model, "LLM_MODEL")

    # Build system prompt
    system_template = load_prompt(config.reasoning.system_prompt)
    system = Template(system_template).render(profile=None)

    # Serialize subgraph to text context
    context_text = serialize_subgraph(subgraph, user_message)

    # Load recent conversation for continuity
    recent_stream = await db.get_session_stream(
        user_id,
        gap_hours=config.reasoning.session_gap_hours,
        limit=config.reasoning.max_recent_messages,
    )

    # Build messages
    messages = _build_messages(context_text, recent_stream, user_message)

    async for token in llm.stream(
        messages=messages,
        model=model,
        system=system,
        temperature=config.reasoning.temperature,
    ):
        yield token


async def reason_and_respond_full(
    user_message: str,
    subgraph: ActiveSubgraph,
    user_id: str,
) -> str:
    """Non-streaming version — returns full response text."""
    tokens = []
    async for token in reason_and_respond(user_message, subgraph, user_id):
        tokens.append(token)
    return "".join(tokens)


async def generate_proactive(
    subgraph: ActiveSubgraph,
    user_id: str,
) -> str | None:
    """
    Generate a proactive message when user opens the app.
    Returns None if nothing warrants speaking.
    """
    config = load_graph_config()
    model = resolve_model(config.reasoning.model, "LLM_MODEL")

    system_template = load_prompt(config.reasoning.system_prompt)
    system = Template(system_template).render(profile=None)

    context_text = serialize_subgraph(subgraph, "")

    # If context is basically empty, don't speak
    if not subgraph.nodes:
        return None

    messages = [
        {
            "role": "user",
            "content": (
                f"{context_text}\n\n"
                "The user just opened the app. Based on the context above, "
                "generate a brief, helpful greeting. If there's something "
                "time-sensitive or important, mention it. If not, a simple "
                "'hey, what's up?' is fine. If there's truly nothing to say, "
                "respond with just SILENT."
            ),
        },
    ]

    response = await llm.generate(
        messages=messages,
        model=model,
        system=system,
        temperature=config.reasoning.temperature,
    )

    if response.strip() == "SILENT":
        return None
    return response


def _build_messages(
    context_text: str,
    recent_stream: list[dict],
    user_message: str,
) -> list[dict]:
    """Build the message list for the reasoning LLM."""
    messages = []

    # Recent conversation history (oldest first)
    for entry in reversed(recent_stream):
        role = entry.get("source", "user")
        if role == "unspool":
            role = "assistant"
        elif role != "user":
            continue
        messages.append({"role": role, "content": entry.get("content", "")})

    # Current message with graph context
    messages.append(
        {
            "role": "user",
            "content": f"{context_text}\n\n{user_message}",
        }
    )

    return messages
