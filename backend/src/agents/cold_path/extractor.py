"""Cold path extractor — with idempotency, semantic dedup, and event-first pattern."""

import hashlib
import json
import uuid

from sqlalchemy import select

from src.agents.cold_path.schemas import ExtractionResult
from src.core.database import AsyncSessionLocal
from src.core.graph import (
    append_event,
    get_or_create_node,
    search_nodes_semantic,
    upsert_edge,
)
from src.core.models import EventStream, GraphNode
from src.core.settings import get_settings
from src.integrations.gemini import (
    get_gemini_client,
    get_embedding,
    get_embeddings_batch,
)
from src.telemetry.error_reporting import report_error
from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

logger = get_logger("cold_path.extractor")

STATUS_OPEN = "OPEN"
STATUS_DONE = "DONE"

# Cosine distance threshold for semantic dedup.
# pgvector cosine_distance = 1 - cosine_similarity, so a distance of 0.1
# means similarity >= 0.9.
_DEDUP_MAX_DISTANCE = 0.1

_EXTRACTION_SYSTEM_INSTRUCTION = """You are the Unspool Archiver. You translate unstructured human messages into a structured Knowledge Graph of nodes and edges.

RULES — follow every one precisely:

1. Every distinct entity is a Node: tasks, people, concepts, emotions, metrics.
2. Every Action/Task MUST have an IS_STATUS edge pointing to a node with content "OPEN".
3. Every date/deadline MUST produce a HAS_DEADLINE edge with an ISO8601 "date" in metadata. Resolve relative dates ("Friday" → the next Friday from Current Time, "tomorrow" → day after Current Time).
4. Metrics (e.g., "ran 5km", "spent $200") produce a TRACKS_METRIC edge with "value" and "unit" in metadata.
5. Related entities get a RELATES_TO edge.
6. If the message is purely conversational ("hey", "thanks", "lol", "👍"), return empty nodes and edges arrays.
7. Nodes: source_content and target_content in edges MUST exactly match a node's content string.
8. Always include "OPEN" as a system_status node when you create any IS_STATUS edge.

EXAMPLE 1 — "I need to finish my thesis by next Friday and call Mom tomorrow"
(assuming Current Time is 2026-03-23)

nodes:
  - content: "finish my thesis", node_type: "action"
  - content: "call Mom", node_type: "action"
  - content: "OPEN", node_type: "system_status"

edges:
  - source_content: "finish my thesis", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "finish my thesis", target_content: "finish my thesis", edge_type: "HAS_DEADLINE", metadata: {"date": "2026-03-27T17:00:00Z"}
  - source_content: "call Mom", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "call Mom", target_content: "call Mom", edge_type: "HAS_DEADLINE", metadata: {"date": "2026-03-24T12:00:00Z"}

EXAMPLE 2 — "I need to buy groceries and my dentist appointment is Thursday at 2pm"

nodes:
  - content: "buy groceries", node_type: "action"
  - content: "dentist appointment", node_type: "action"
  - content: "OPEN", node_type: "system_status"

edges:
  - source_content: "buy groceries", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "dentist appointment", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "dentist appointment", target_content: "dentist appointment", edge_type: "HAS_DEADLINE", metadata: {"date": "2026-03-26T14:00:00Z"}

EXAMPLE 3 — "ran 5km this morning, feeling pretty good"

nodes:
  - content: "ran 5km", node_type: "action"
  - content: "running", node_type: "metric"
  - content: "feeling good", node_type: "emotion"

edges:
  - source_content: "ran 5km", target_content: "running", edge_type: "TRACKS_METRIC", metadata: {"value": 5.0, "unit": "km"}
  - source_content: "ran 5km", target_content: "feeling good", edge_type: "EXPERIENCED_DURING"
"""


async def ensure_status_nodes(session, user_id: uuid.UUID):
    open_node = await get_or_create_node(session, user_id, STATUS_OPEN, "system_status")
    done_node = await get_or_create_node(session, user_id, STATUS_DONE, "system_status")
    return open_node, done_node


@observe(name="cold_path.extraction")
async def run_extraction(
    raw_message: str, current_time_iso: str, timezone: str,
) -> ExtractionResult:
    """Uses Gemini with structured outputs to parse a brain dump into a Graph.

    Uses EXTRACTION_MODEL (not BACKGROUND_MODEL) because graph quality is the
    foundation of the entire product — cheap extractions that miss edges or
    relationships degrade everything downstream.

    Gemini SDK usage follows https://ai.google.dev/gemini-api/docs/structured-output:
    - system_instruction: separates instructions from user content
    - response_mime_type: "application/json" for structured output
    - response_json_schema: Pydantic model's JSON schema
    - thinking_config: high budget for accurate extraction
    - temperature: 0 for deterministic output
    """
    from google.genai import types

    settings = get_settings()
    client = get_gemini_client()

    user_content = f"Current Time: {current_time_iso}\nUser Timezone: {timezone}\n\n{raw_message}"

    response = await client.aio.models.generate_content(
        model=settings.EXTRACTION_MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=ExtractionResult.model_json_schema(),
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_budget=8192),
        ),
    )

    parsed = json.loads(response.text)
    return ExtractionResult(**parsed)


async def _find_semantic_match(
    session, user_id: uuid.UUID, content: str, node_type: str,
) -> GraphNode | None:
    """Return an existing node only if cosine similarity >= 0.9.

    Uses pgvector's cosine_distance ordering with an explicit max_distance
    filter so that dissimilar nodes are never returned, regardless of how
    small the graph is.

    Uses SEMANTIC_SIMILARITY task_type for dedup comparisons as recommended
    by https://ai.google.dev/gemini-api/docs/embeddings.
    """
    try:
        embedding = await get_embedding(content, task_type="SEMANTIC_SIMILARITY")
        matches = await search_nodes_semantic(
            session,
            user_id,
            embedding,
            limit=1,
            node_type=node_type,
            max_distance=_DEDUP_MAX_DISTANCE,
        )
        if matches:
            return matches[0]
    except Exception:
        logger.warning("cold_path.semantic_match_failed", content=content, exc_info=True)
    return None


def _idempotency_key(user_id: str, message: str) -> str:
    """Hash of user_id + message for cold path idempotency."""
    return hashlib.sha256(f"{user_id}:{message}".encode()).hexdigest()[:16]


@observe(name="cold_path.process")
async def process_brain_dump(
    user_id: uuid.UUID,
    raw_message: str,
    current_time_iso: str,
    timezone: str,
    trace_id: str | None = None,
) -> None:
    """The main entry point for the Cold Path Archiver. Idempotent."""
    idem_key = _idempotency_key(str(user_id), raw_message)

    async with AsyncSessionLocal() as session:
        # Check idempotency — skip if already processed
        existing = await session.execute(
            select(EventStream).where(
                EventStream.user_id == user_id,
                EventStream.event_type == "ColdPathProcessed",
                EventStream.payload["idempotency_key"].as_string() == idem_key,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.info("cold_path.skipped_duplicate", user_id=str(user_id))
            return

        logger.info("cold_path.start", user_id=str(user_id), trace_id=trace_id)

        # Ensure system nodes exist
        await ensure_status_nodes(session, user_id)

        # Run LLM extraction
        try:
            extraction = await run_extraction(raw_message, current_time_iso, timezone)
        except Exception as e:
            report_error(
                "cold_path.extraction_failed", e,
                user_id=str(user_id), trace_id=trace_id,
            )
            return

        if not extraction.nodes and not extraction.edges:
            logger.info("cold_path.no_entities", user_id=str(user_id))
            await append_event(session, user_id, "ColdPathProcessed", {
                "idempotency_key": idem_key, "nodes": 0, "edges": 0,
            })
            await session.commit()
            return

        logger.info(
            "cold_path.extracted",
            nodes=len(extraction.nodes),
            edges=len(extraction.edges),
        )

        # Create nodes with semantic dedup
        node_map: dict[str, uuid.UUID] = {}

        # Separate nodes that need dedup check vs new nodes
        nodes_to_embed: list[str] = []
        nodes_to_embed_types: list[str] = []

        for enode in extraction.nodes:
            if not enode.content or not enode.content.strip():
                continue
            existing_node = await _find_semantic_match(
                session, user_id, enode.content, enode.node_type,
            )
            if existing_node:
                node_map[enode.content] = existing_node.id
                logger.debug(
                    "cold_path.dedup_match",
                    content=enode.content,
                    matched=existing_node.content,
                )
            else:
                nodes_to_embed.append(enode.content)
                nodes_to_embed_types.append(enode.node_type)

        # Batch-embed all new nodes in a single API call
        # Uses RETRIEVAL_DOCUMENT task_type for storage as per Gemini docs
        embeddings: list[list[float] | None] = []
        if nodes_to_embed:
            try:
                embeddings = await get_embeddings_batch(
                    nodes_to_embed, task_type="RETRIEVAL_DOCUMENT",
                )
            except Exception:
                logger.warning("cold_path.batch_embed_failed", exc_info=True)
                embeddings = [None] * len(nodes_to_embed)

        for content, node_type, embedding in zip(
            nodes_to_embed, nodes_to_embed_types, embeddings,
        ):
            db_node = await get_or_create_node(
                session, user_id, content, node_type, embedding,
            )
            node_map[content] = db_node.id

        # Ensure status nodes in map
        open_node, done_node = await ensure_status_nodes(session, user_id)
        node_map[STATUS_OPEN] = open_node.id
        node_map[STATUS_DONE] = done_node.id

        # Create edges
        for edge in extraction.edges:
            source_id = node_map.get(edge.source_content)
            target_id = node_map.get(edge.target_content)

            if not source_id or not target_id:
                logger.warning(
                    "cold_path.edge_skipped",
                    source=edge.source_content,
                    target=edge.target_content,
                )
                continue

            await upsert_edge(
                session=session,
                user_id=user_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=edge.edge_type,
                metadata=edge.metadata.model_dump(exclude_none=True) if edge.metadata else {},
            )

        # Mark as processed
        await append_event(session, user_id, "ColdPathProcessed", {
            "idempotency_key": idem_key,
            "nodes": len(extraction.nodes),
            "edges": len(extraction.edges),
        })

        await session.commit()
        logger.info("cold_path.complete", user_id=str(user_id), trace_id=trace_id)
