"""Cold path extractor — with idempotency, semantic dedup, and event-first pattern."""

import hashlib
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
from src.integrations.openai import get_openai_client, get_embedding
from src.telemetry.error_reporting import report_error
from src.telemetry.logger import get_logger

logger = get_logger("cold_path.extractor")

STATUS_OPEN = "OPEN"
STATUS_DONE = "DONE"

# Cosine distance threshold for semantic dedup.
# pgvector cosine_distance = 1 - cosine_similarity, so a distance of 0.1
# means similarity >= 0.9.
_DEDUP_MAX_DISTANCE = 0.1


async def ensure_status_nodes(session, user_id: uuid.UUID):
    open_node = await get_or_create_node(session, user_id, STATUS_OPEN, "system_status")
    done_node = await get_or_create_node(session, user_id, STATUS_DONE, "system_status")
    return open_node, done_node


async def run_extraction(
    raw_message: str, current_time_iso: str, timezone: str,
) -> ExtractionResult:
    """Uses GPT with Structured Outputs to parse a brain dump into a Graph."""
    settings = get_settings()
    client = get_openai_client()

    system_prompt = f"""You are the Unspool Archiver, an expert at translating unstructured human brain dumps into a structured Knowledge Graph.

Current Time: {current_time_iso}
User Timezone: {timezone}

CRITICAL RULES:
1. Everything is a Node. If a user has a task, the task is a Node.
2. If a user describes a Task or Action item, create an 'action' node AND an edge of type 'IS_STATUS' pointing to a node with content 'OPEN'.
3. If a user describes an event with a date, create an edge of type 'HAS_DEADLINE' and put the exact ISO8601 timestamp in the metadata under the key 'date'.
4. If a user tracks a metric (e.g., "smoked 3 cigs"), create a 'concept' node for the metric, an 'action' node for the event, and a 'TRACKS_METRIC' edge.
5. De-duplicate concepts where possible.
6. If the message is purely conversational ("hey", "thanks", "lol"), return empty nodes and edges arrays.
"""

    response = await client.beta.chat.completions.parse(
        model=settings.LLM_MODEL_FAST,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_message},
        ],
        response_format=ExtractionResult,
    )

    return response.choices[0].message.parsed


async def _find_semantic_match(
    session, user_id: uuid.UUID, content: str, node_type: str,
) -> GraphNode | None:
    """Return an existing node only if cosine similarity >= 0.9.

    Uses pgvector's cosine_distance ordering with an explicit max_distance
    filter so that dissimilar nodes are never returned, regardless of how
    small the graph is.
    """
    try:
        embedding = await get_embedding(content)
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
        logger.debug("cold_path.semantic_match_failed", content=content, exc_info=True)
    return None


def _idempotency_key(user_id: str, message: str) -> str:
    """Hash of user_id + message for cold path idempotency."""
    return hashlib.sha256(f"{user_id}:{message}".encode()).hexdigest()[:16]


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

        for enode in extraction.nodes:
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
                try:
                    embedding = await get_embedding(enode.content)
                except Exception:
                    embedding = None
                db_node = await get_or_create_node(
                    session, user_id, enode.content, enode.node_type, embedding,
                )
                node_map[enode.content] = db_node.id

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
