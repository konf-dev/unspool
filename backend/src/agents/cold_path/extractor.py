"""Cold path extractor — with idempotency, semantic dedup, session-level extraction, and status lock."""

import asyncio
import hashlib
import json
import uuid

from sqlalchemy import select, and_

from src.agents.cold_path.schemas import ExtractionResult
from src.core.config_loader import hp
from src.core.database import AsyncSessionLocal
from src.core.graph import (
    append_edge,
    append_event,
    create_node_event,
    get_or_create_node,
    search_nodes_semantic,
    upsert_edge,
)
from src.core.models import EventStream, GraphNode, GraphEdge
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


_EXTRACTION_SYSTEM_INSTRUCTION = """You are the Unspool Archiver. You translate unstructured human messages into a structured Knowledge Graph of nodes and edges.

RULES — follow every one precisely:

1. Default node_type is "memory" (catch-all). Only use "person" for people, "system_status" for OPEN/DONE.
2. Every node gets metadata with entities, temporal info, quantities, and actionable flag.
3. actionable: false for past-tense activities ("spent $50", "ran 5km", "bought milk"), emotions, and facts.
4. actionable: true for future-oriented items ("need to buy", "finish by Friday", "call Mom").
5. Status updates ("done with X", "finished Y") → return EMPTY nodes and edges arrays. The hot path handles status.
6. Meta-instructions ("start tracking X", "remind me at X") → return EMPTY nodes and edges arrays. The hot path handles these.
7. Every actionable item MUST have an IS_STATUS edge pointing to a node with content "OPEN".
8. Always include "OPEN" as a system_status node when you create any IS_STATUS edge.
9. Every date/deadline MUST produce a HAS_DEADLINE edge with full ISO8601 timestamp in metadata (not date-only). Include deadline_type: "hard", "soft", or "routine".
10. Metrics (e.g., "ran 5km", "spent $200") produce a TRACKS_METRIC edge with "value", "unit", and "logged_at" (= Current Time) in metadata.
11. Related entities get a RELATES_TO edge.
12. Nodes: source_content and target_content in edges MUST exactly match a node's content string.
13. If the message is purely conversational ("hey", "thanks", "lol", "👍"), return empty nodes and edges arrays.
14. When processing a FULL SESSION, extract the final state — only keep final versions after corrections. If something was marked done, don't create it as open. EXCEPTION: for metrics (spending, exercise, measurements), extract EVERY individual entry as a separate node with its own TRACKS_METRIC edge — never consolidate or summarize metric data points.

EXAMPLE 1 — "I need to finish my thesis by next Friday and call Mom tomorrow"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "finish my thesis", node_type: "memory", metadata: {entities: [{text: "thesis", likely: "project"}], temporal: {tense: "future", dates: ["2026-03-28T17:00:00Z"]}, quantities: [], actionable: true}
  - content: "call Mom", node_type: "memory", metadata: {entities: [{text: "Mom", likely: "person"}], temporal: {tense: "future", dates: ["2026-03-24T12:00:00Z"]}, quantities: [], actionable: true}
  - content: "Mom", node_type: "person", metadata: {entities: [{text: "Mom", likely: "person"}], temporal: {}, quantities: [], actionable: false}
  - content: "OPEN", node_type: "system_status", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "finish my thesis", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "finish my thesis", target_content: "finish my thesis", edge_type: "HAS_DEADLINE", metadata: {date: "2026-03-28T17:00:00Z", deadline_type: "hard"}
  - source_content: "call Mom", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "call Mom", target_content: "call Mom", edge_type: "HAS_DEADLINE", metadata: {date: "2026-03-24T12:00:00Z", deadline_type: "soft"}
  - source_content: "call Mom", target_content: "Mom", edge_type: "RELATES_TO"

EXAMPLE 2 — "I need to buy groceries and my dentist appointment is Thursday at 2pm"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "buy groceries", node_type: "memory", metadata: {entities: [{text: "groceries", likely: "errand"}], temporal: {tense: "future"}, quantities: [], actionable: true}
  - content: "dentist appointment", node_type: "memory", metadata: {entities: [{text: "dentist", likely: "appointment"}], temporal: {tense: "future", dates: ["2026-03-27T14:00:00Z"]}, quantities: [], actionable: true}
  - content: "OPEN", node_type: "system_status", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "buy groceries", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "dentist appointment", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "dentist appointment", target_content: "dentist appointment", edge_type: "HAS_DEADLINE", metadata: {date: "2026-03-27T14:00:00Z", deadline_type: "hard"}

EXAMPLE 3 — "ran 5km this morning, feeling pretty good"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "ran 5km", node_type: "memory", metadata: {entities: [], temporal: {tense: "past", dates: ["2026-03-23T08:00:00Z"]}, quantities: [{value: 5, unit: "km"}], actionable: false}
  - content: "running", node_type: "memory", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}
  - content: "feeling good", node_type: "memory", metadata: {entities: [], temporal: {tense: "present"}, quantities: [], actionable: false}

edges:
  - source_content: "ran 5km", target_content: "running", edge_type: "TRACKS_METRIC", metadata: {value: 5.0, unit: "km", logged_at: "2026-03-23T10:00:00Z"}
  - source_content: "ran 5km", target_content: "feeling good", edge_type: "EXPERIENCED_DURING"

EXAMPLE 4 — "my car registration expires next month"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "renew car registration", node_type: "memory", metadata: {entities: [{text: "car registration", likely: "document"}], temporal: {tense: "future", dates: ["2026-04-23T17:00:00Z"]}, quantities: [], actionable: true}
  - content: "OPEN", node_type: "system_status", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "renew car registration", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "renew car registration", target_content: "renew car registration", edge_type: "HAS_DEADLINE", metadata: {date: "2026-04-23T17:00:00Z", deadline_type: "soft"}

Note: Implicit task. "expires next month" means the user needs to renew it.

EXAMPLE 5 — "my boss keeps piling things on and I'm losing it"

nodes:
  - content: "feeling overwhelmed at work", node_type: "memory", metadata: {entities: [{text: "boss", likely: "person"}], temporal: {tense: "present"}, quantities: [], actionable: false}

edges: []

Note: Venting, not a task. No action items from emotional statements.

EXAMPLE 6 — "finish report before the presentation on Friday"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "finish report", node_type: "memory", metadata: {entities: [{text: "report", likely: "project"}], temporal: {tense: "future", dates: ["2026-03-28T17:00:00Z"]}, quantities: [], actionable: true}
  - content: "presentation", node_type: "memory", metadata: {entities: [{text: "presentation", likely: "event"}], temporal: {tense: "future", dates: ["2026-03-28T17:00:00Z"]}, quantities: [], actionable: true}
  - content: "OPEN", node_type: "system_status", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "finish report", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "presentation", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "finish report", target_content: "presentation", edge_type: "DEPENDS_ON"
  - source_content: "presentation", target_content: "presentation", edge_type: "HAS_DEADLINE", metadata: {date: "2026-03-28T17:00:00Z", deadline_type: "hard"}

EXAMPLE 7 — "take meds every morning at 8am"
(assuming Current Time is 2026-03-23T10:00:00Z)

nodes:
  - content: "take meds", node_type: "memory", metadata: {entities: [{text: "meds", likely: "health"}], temporal: {tense: "future", dates: ["2026-03-24T08:00:00Z"]}, quantities: [], actionable: true}
  - content: "OPEN", node_type: "system_status", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "take meds", target_content: "OPEN", edge_type: "IS_STATUS"
  - source_content: "take meds", target_content: "take meds", edge_type: "HAS_DEADLINE", metadata: {date: "2026-03-24T08:00:00Z", deadline_type: "routine"}

EXAMPLE 8 (NEGATIVE) — "Spent $50 on groceries"

nodes:
  - content: "spent $50 on groceries", node_type: "memory", metadata: {entities: [{text: "$50", likely: "currency", value: 50, unit: "USD"}, {text: "groceries", likely: "category"}], temporal: {tense: "past"}, quantities: [{value: 50, unit: "USD"}], actionable: false}
  - content: "spending", node_type: "memory", metadata: {entities: [], temporal: {}, quantities: [], actionable: false}

edges:
  - source_content: "spent $50 on groceries", target_content: "spending", edge_type: "TRACKS_METRIC", metadata: {value: 50.0, unit: "USD", logged_at: "CURRENT_TIME"}

Note: Past tense + actionable: false. NOT an open task. No IS_STATUS edge.

EXAMPLE 9 (NEGATIVE) — "Done with groceries"

nodes: []
edges: []

Note: Status update. The hot path handles this via mutate_graph SET_STATUS DONE. Return empty.

EXAMPLE 10 (NEGATIVE) — "Start tracking my spending"

nodes: []
edges: []

Note: Meta-instruction. The hot path or system handles tracking setup. Return empty.

EXAMPLE 11 (NEGATIVE) — "Remind me at 5pm to take meds"

nodes: []
edges: []

Note: Reminder request. The hot path schedule_reminder tool handles this. Return empty.

EXAMPLE 12 — Purely conversational: "hey", "thanks", "lol", "👍"

nodes: []
edges: []
"""


async def ensure_status_nodes(session, user_id: uuid.UUID):
    open_node = await get_or_create_node(session, user_id, STATUS_OPEN, "system_status")
    done_node = await get_or_create_node(session, user_id, STATUS_DONE, "system_status")
    return open_node, done_node


@observe(name="cold_path.extraction")
async def run_extraction(
    raw_message: str,
    current_time_iso: str,
    timezone: str,
    recent_messages: list[str] | None = None,
) -> ExtractionResult:
    """Uses Gemini with structured outputs to parse a brain dump into a Graph.

    Includes exponential backoff retry for transient 503/UNAVAILABLE errors.
    """
    from google.genai import types

    settings = get_settings()
    client = get_gemini_client()

    # Include recent conversation context for anaphora resolution
    context_prefix = ""
    if recent_messages:
        context_lines = "\n".join(f"- {m}" for m in recent_messages[-3:])
        context_prefix = f"Recent conversation (for context only — extract from the LAST message):\n{context_lines}\n\n"

    user_content = f"Current Time: {current_time_iso}\nUser Timezone: {timezone}\n\n{context_prefix}{raw_message}"

    last_error = None
    for attempt in range(int(hp("extraction", "max_retries", 3))):
        try:
            response = await client.aio.models.generate_content(
                model=settings.EXTRACTION_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_json_schema=ExtractionResult.model_json_schema(),
                    temperature=hp("extraction", "llm_temperature", 0),
                    thinking_config=types.ThinkingConfig(thinking_budget=hp("extraction", "llm_thinking_budget", 8192)),
                ),
            )

            parsed = json.loads(response.text)
            return ExtractionResult(**parsed)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_transient = "503" in error_str or "unavailable" in error_str or "service_unavailable" in error_str
            if is_transient and attempt < int(hp("extraction", "max_retries", 3)) - 1:
                delay = float(hp("extraction", "retry_base_delay", 1.0)) * (2 ** attempt)
                logger.warning(
                    "cold_path.extraction_retry",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise last_error  # Should not reach here, but safety net


@observe(name="cold_path.session_extraction")
async def run_session_extraction(
    messages: list[dict],
    current_time_iso: str,
    timezone: str,
) -> ExtractionResult:
    """Extract from a full conversation session — sees corrections, full arc, produces net state."""
    from google.genai import types

    settings = get_settings()
    client = get_gemini_client()

    # Build session transcript
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            lines.append(f"[{role}]: {content}")

    session_text = "\n".join(lines)

    session_preamble = (
        "You are reviewing a COMPLETE conversation session. "
        "Extract what facts, tasks, and information should be remembered after this conversation. "
        "If something was mentioned then corrected or cancelled, only keep the final version. "
        "If something was marked done during the conversation, don't create it as an open item.\n\n"
        "IMPORTANT — metrics and tracked quantities (spending, exercise, measurements, etc.): "
        "extract EVERY individual entry as a separate node with its own TRACKS_METRIC edge. "
        "Do NOT consolidate or summarize multiple metric entries. "
        "For example, if the user mentioned '$50 on groceries' and '$30 on gas', those are TWO separate nodes, not one summary.\n\n"
    )

    user_content = f"Current Time: {current_time_iso}\nUser Timezone: {timezone}\n\n{session_preamble}Session transcript:\n{session_text}"

    last_error = None
    for attempt in range(int(hp("extraction", "max_retries", 3))):
        try:
            response = await client.aio.models.generate_content(
                model=settings.EXTRACTION_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_json_schema=ExtractionResult.model_json_schema(),
                    temperature=hp("extraction", "llm_temperature", 0),
                    thinking_config=types.ThinkingConfig(thinking_budget=hp("extraction", "llm_thinking_budget", 8192)),
                ),
            )

            parsed = json.loads(response.text)
            return ExtractionResult(**parsed)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_transient = "503" in error_str or "unavailable" in error_str or "service_unavailable" in error_str
            if is_transient and attempt < int(hp("extraction", "max_retries", 3)) - 1:
                delay = float(hp("extraction", "retry_base_delay", 1.0)) * (2 ** attempt)
                logger.warning(
                    "cold_path.session_extraction_retry",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise last_error


async def _find_semantic_match(
    session, user_id: uuid.UUID, content: str, node_type: str,
    embedding: list[float] | None = None,
) -> tuple[GraphNode | None, list[float] | None]:
    """Return an existing node only if cosine similarity >= 0.9.

    Accepts a pre-computed embedding to avoid redundant API calls during
    cross-type dedup. Returns (match, embedding) so callers can reuse it.
    """
    try:
        if embedding is None:
            embedding = await get_embedding(content, task_type="SEMANTIC_SIMILARITY")
        matches = await search_nodes_semantic(
            session,
            user_id,
            embedding,
            limit=1,
            node_type=node_type,
            max_distance=float(hp("extraction", "dedup_max_distance", 0.1)),
        )
        if matches:
            return matches[0], embedding
    except Exception:
        logger.warning("cold_path.semantic_match_failed", content=content, exc_info=True)
    return None, embedding


async def _node_has_done_status(
    session, user_id: uuid.UUID, node_id: uuid.UUID,
    done_node_id: uuid.UUID | None = None,
) -> bool:
    """Check if a node already has IS_STATUS→DONE (status lock guard).

    Accepts a pre-fetched ``done_node_id`` to avoid redundant lookups when
    called in a loop.
    """
    if done_node_id is None:
        done_node = (await session.execute(
            select(GraphNode).where(
                GraphNode.user_id == user_id,
                GraphNode.content == STATUS_DONE,
                GraphNode.node_type == "system_status",
            )
        )).scalar_one_or_none()
        if not done_node:
            return False
        done_node_id = done_node.id

    existing = (await session.execute(
        select(GraphEdge).where(
            and_(
                GraphEdge.user_id == user_id,
                GraphEdge.source_node_id == node_id,
                GraphEdge.target_node_id == done_node_id,
                GraphEdge.edge_type == "IS_STATUS",
            )
        )
    )).scalar_one_or_none()

    return existing is not None


def _idempotency_key(user_id: str, message: str) -> str:
    """Hash of user_id + message for cold path idempotency."""
    return hashlib.sha256(f"{user_id}:{message}".encode()).hexdigest()[:16]


def _session_idempotency_key(user_id: str, session_id: str) -> str:
    """Hash of user_id + session_id for session-level idempotency."""
    return hashlib.sha256(f"{user_id}:session:{session_id}".encode()).hexdigest()[:16]


async def _create_nodes_and_edges(
    session, user_id: uuid.UUID, extraction: ExtractionResult,
) -> tuple[int, int]:
    """Create nodes and edges from extraction result. Returns (node_count, edge_count).

    Includes status lock: skips IS_STATUS→OPEN edges if node already has DONE status.
    """
    # Ensure system nodes exist
    await ensure_status_nodes(session, user_id)

    if not extraction.nodes and not extraction.edges:
        return 0, 0

    # Maps content string → node UUID.  For metric source nodes that may have
    # identical content (e.g. "spent $50 on groceries" twice), we use indexed
    # keys like "content\x00#1" to avoid collision.  The edge loop below uses
    # _resolve_node_id() to look up the correct key for each edge.
    node_map: dict[str, uuid.UUID] = {}

    # Track how many times each metric-source content has been seen, so we can
    # assign unique keys and later match edges to the right node.
    _metric_content_counter: dict[str, int] = {}

    nodes_to_embed: list[str] = []
    nodes_to_embed_types: list[str] = []
    nodes_to_embed_metadata: list[dict] = []
    nodes_force_create: list[bool] = []
    # Parallel list: the key under which each new node will be stored in node_map
    nodes_map_keys: list[str] = []

    # Types that are semantically equivalent for dedup purposes
    _EQUIVALENT_TYPES = {"memory", "action", "concept"}

    # Identify nodes that source TRACKS_METRIC edges — never dedup these
    _metric_source_contents = {
        edge.source_content
        for edge in extraction.edges
        if edge.edge_type == "TRACKS_METRIC"
    }

    for enode in extraction.nodes:
        if not enode.content or not enode.content.strip():
            continue

        # Metric source nodes: always create new, use indexed key to avoid collision
        if enode.content in _metric_source_contents:
            idx = _metric_content_counter.get(enode.content, 0)
            _metric_content_counter[enode.content] = idx + 1
            map_key = f"{enode.content}\x00#{idx}"
            logger.debug("cold_path.skip_dedup_metric", content=enode.content, index=idx)
            nodes_to_embed.append(enode.content)
            nodes_to_embed_types.append(enode.node_type)
            nodes_to_embed_metadata.append(enode.metadata.model_dump() if enode.metadata else {})
            nodes_force_create.append(True)
            nodes_map_keys.append(map_key)
            continue

        # Search for semantic match — try exact type first, then equivalent types.
        # Reuse the embedding across type checks to avoid redundant API calls.
        existing_node, cached_embedding = await _find_semantic_match(
            session, user_id, enode.content, enode.node_type,
        )
        if not existing_node and enode.node_type in _EQUIVALENT_TYPES:
            for alt_type in _EQUIVALENT_TYPES - {enode.node_type}:
                existing_node, cached_embedding = await _find_semantic_match(
                    session, user_id, enode.content, alt_type,
                    embedding=cached_embedding,
                )
                if existing_node:
                    break
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
            nodes_to_embed_metadata.append(enode.metadata.model_dump() if enode.metadata else {})
            nodes_force_create.append(False)
            nodes_map_keys.append(enode.content)

    # Batch-embed all new nodes — retry with backoff on transient failures
    embeddings: list[list[float] | None] = []
    if nodes_to_embed:
        for attempt in range(int(hp("embedding", "retry_max_attempts", 3))):
            try:
                embeddings = await get_embeddings_batch(
                    nodes_to_embed, task_type="RETRIEVAL_DOCUMENT",
                )
                break
            except Exception:
                if attempt < int(hp("embedding", "retry_max_attempts", 3)) - 1:
                    delay = float(hp("embedding", "retry_backoff_base", 2.0)) ** attempt
                    logger.warning(
                        "cold_path.batch_embed_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("cold_path.batch_embed_failed", exc_info=True)
                    embeddings = [None] * len(nodes_to_embed)

    for map_key, content, node_type, embedding, metadata, force_new in zip(
        nodes_map_keys, nodes_to_embed, nodes_to_embed_types,
        embeddings, nodes_to_embed_metadata, nodes_force_create,
    ):
        if force_new:
            db_node = await create_node_event(
                session, user_id, content, node_type, embedding,
            )
            if metadata:
                db_node.metadata_ = metadata
        else:
            db_node = await get_or_create_node(
                session, user_id, content, node_type, embedding, metadata=metadata,
            )
        node_map[map_key] = db_node.id

    # Ensure status nodes in map
    open_node, done_node = await ensure_status_nodes(session, user_id)
    node_map[STATUS_OPEN] = open_node.id
    node_map[STATUS_DONE] = done_node.id

    # Build a counter to assign each TRACKS_METRIC edge to its corresponding
    # indexed source node.  The N-th TRACKS_METRIC edge with source_content X
    # maps to node_map["X\x00#N"].
    _edge_metric_counter: dict[str, int] = {}

    def _resolve_id(content: str, is_metric_source: bool) -> uuid.UUID | None:
        """Look up a node UUID, handling indexed keys for metric sources."""
        if is_metric_source:
            idx = _edge_metric_counter.get(content, 0)
            _edge_metric_counter[content] = idx + 1
            return node_map.get(f"{content}\x00#{idx}")
        return node_map.get(content)

    # Create edges with status lock
    edges_created = 0
    for edge in extraction.edges:
        is_metric_edge = edge.edge_type == "TRACKS_METRIC"
        source_id = _resolve_id(edge.source_content, is_metric_edge)
        target_id = node_map.get(edge.target_content)

        if not source_id or not target_id:
            logger.warning(
                "cold_path.edge_skipped",
                source=edge.source_content,
                target=edge.target_content,
            )
            continue

        # Status lock: don't create IS_STATUS→OPEN if node already has DONE
        if edge.edge_type == "IS_STATUS" and edge.target_content == STATUS_OPEN:
            if await _node_has_done_status(session, user_id, source_id, done_node_id=done_node.id):
                logger.info(
                    "cold_path.status_lock_skipped",
                    source=edge.source_content,
                    reason="node already DONE, hot path wins",
                )
                continue

        edge_meta = edge.metadata.model_dump(exclude_none=True) if edge.metadata else {}

        if edge.edge_type == "TRACKS_METRIC":
            # A1: always INSERT for metrics — never overwrite previous entries
            await append_edge(
                session=session,
                user_id=user_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=edge.edge_type,
                metadata=edge_meta,
            )
        else:
            await upsert_edge(
                session=session,
                user_id=user_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=edge.edge_type,
                metadata=edge_meta,
            )
        edges_created += 1

    return len(extraction.nodes), edges_created


@observe(name="cold_path.process")
async def process_brain_dump(
    user_id: uuid.UUID,
    raw_message: str,
    current_time_iso: str,
    timezone: str,
    trace_id: str | None = None,
    recent_messages: list[str] | None = None,
    retry_count: int = 0,
) -> None:
    """The main entry point for the Cold Path Archiver (single message). Idempotent."""
    idem_key = _idempotency_key(str(user_id), raw_message)

    # Convert idempotency key to a stable int for pg_advisory_xact_lock
    idem_lock_id = int(idem_key, 16) % (2**63)

    async with AsyncSessionLocal() as session:
        # Acquire a transaction-scoped advisory lock to prevent concurrent
        # processing of the same message (e.g., QStash retry racing the original)
        from sqlalchemy import text
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": idem_lock_id})

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

        # Run LLM extraction (A6: retry via QStash on failure)
        try:
            extraction = await run_extraction(raw_message, current_time_iso, timezone, recent_messages)
        except Exception as e:
            report_error(
                "cold_path.extraction_failed", e,
                user_id=str(user_id), trace_id=trace_id,
            )
            # Dispatch retry with exponential backoff via QStash
            max_retries = int(hp("extraction", "max_retries", 3))
            if retry_count < max_retries:
                try:
                    from src.integrations.qstash import dispatch_job
                    delay = int(60 * (2 ** retry_count))  # 60s, 120s, 240s
                    await dispatch_job("process-message", {
                        "user_id": str(user_id),
                        "message": raw_message,
                        "trace_id": trace_id,
                        "retry_count": retry_count + 1,
                    }, delay=delay)
                    logger.info(
                        "cold_path.extraction_retry_queued",
                        user_id=str(user_id),
                        retry_count=retry_count + 1,
                        delay=delay,
                    )
                except Exception:
                    logger.error("cold_path.retry_dispatch_failed", exc_info=True)
            else:
                logger.error(
                    "cold_path.extraction_retries_exhausted",
                    user_id=str(user_id),
                    trace_id=trace_id,
                    retry_count=retry_count,
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

        node_count, edge_count = await _create_nodes_and_edges(session, user_id, extraction)

        # Mark as processed
        await append_event(session, user_id, "ColdPathProcessed", {
            "idempotency_key": idem_key,
            "nodes": node_count,
            "edges": edge_count,
        })

        await session.commit()
        logger.info("cold_path.complete", user_id=str(user_id), trace_id=trace_id)


@observe(name="cold_path.process_session")
async def process_session(
    user_id: uuid.UUID,
    session_id: str,
    trace_id: str | None = None,
) -> None:
    """Session-level extraction — processes the full conversation at once. Idempotent."""
    from datetime import datetime, timezone as tz
    from src.db.queries import get_profile

    idem_key = _session_idempotency_key(str(user_id), session_id)
    idem_lock_id = int(idem_key, 16) % (2**63)

    async with AsyncSessionLocal() as db_session:
        # Advisory lock to prevent concurrent session processing
        from sqlalchemy import text as sa_text
        await db_session.execute(sa_text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": idem_lock_id})

        # Check idempotency
        existing = await db_session.execute(
            select(EventStream).where(
                EventStream.user_id == user_id,
                EventStream.event_type == "SessionConsolidated",
                EventStream.payload["idempotency_key"].as_string() == idem_key,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.info("cold_path.session_skipped_duplicate", user_id=str(user_id), session_id=session_id)
            return

        logger.info("cold_path.session_start", user_id=str(user_id), session_id=session_id, trace_id=trace_id)

        # Load ALL messages for this session from EventStream
        result = await db_session.execute(
            select(EventStream).where(
                EventStream.user_id == user_id,
                EventStream.event_type.in_(["MessageReceived", "AgentReplied"]),
                EventStream.payload["metadata"]["session_id"].as_string() == session_id,
            ).order_by(EventStream.created_at)
        )
        events = result.scalars().all()

        if not events:
            logger.info("cold_path.session_no_messages", user_id=str(user_id), session_id=session_id)
            return

        messages = []
        for evt in events:
            role = "user" if evt.event_type == "MessageReceived" else "assistant"
            content = (evt.payload or {}).get("content", "")
            if content:
                messages.append({"role": role, "content": content})

        if not messages:
            return

        # Get user profile for timezone
        profile = await get_profile(str(user_id))
        user_tz = (profile.get("timezone") if profile else None) or "UTC"
        current_time_iso = datetime.now(tz.utc).isoformat()

        # Run session-level extraction
        try:
            extraction = await run_session_extraction(messages, current_time_iso, user_tz)
        except Exception as e:
            report_error(
                "cold_path.session_extraction_failed", e,
                user_id=str(user_id), session_id=session_id, trace_id=trace_id,
            )
            return

        if not extraction.nodes and not extraction.edges:
            logger.info("cold_path.session_no_entities", user_id=str(user_id))
            await append_event(db_session, user_id, "SessionConsolidated", {
                "idempotency_key": idem_key,
                "session_id": session_id,
                "nodes": 0,
                "edges": 0,
            })
            await db_session.commit()
            return

        logger.info(
            "cold_path.session_extracted",
            nodes=len(extraction.nodes),
            edges=len(extraction.edges),
        )

        node_count, edge_count = await _create_nodes_and_edges(db_session, user_id, extraction)

        # Mark session as consolidated
        await append_event(db_session, user_id, "SessionConsolidated", {
            "idempotency_key": idem_key,
            "session_id": session_id,
            "nodes": node_count,
            "edges": edge_count,
        })

        await db_session.commit()
        logger.info("cold_path.session_complete", user_id=str(user_id), session_id=session_id, trace_id=trace_id)
