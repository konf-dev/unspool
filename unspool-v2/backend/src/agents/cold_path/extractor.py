import logging
from typing import Dict, Any, List
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
import json

from src.core.config import settings
from src.core.graph import get_or_create_node, upsert_edge
from src.agents.cold_path.schemas import ExtractionResult, ExtractedNode, ExtractedEdge

logger = logging.getLogger(__name__)

# Initialize the OpenAI client natively for Structured Outputs
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Define standard system status nodes
STATUS_OPEN = "OPEN"
STATUS_DONE = "DONE"

async def ensure_status_nodes(session: AsyncSession, user_id: uuid.UUID):
    """Ensures that the fundamental system nodes exist for the user."""
    open_node = await get_or_create_node(session, user_id, STATUS_OPEN, "system_status")
    done_node = await get_or_create_node(session, user_id, STATUS_DONE, "system_status")
    return open_node, done_node

async def run_extraction(raw_message: str, current_time_iso: str, timezone: str) -> ExtractionResult:
    """Uses GPT-4o-mini with Structured Outputs to parse a brain dump into a Graph."""
    
    system_prompt = f"""You are the Unspool Archiver, an expert at translating unstructured human brain dumps into a structured Knowledge Graph.
    
Current Time: {current_time_iso}
User Timezone: {timezone}

CRITICAL RULES:
1. Everything is a Node. If a user has a task, the task is a Node.
2. If a user describes a Task or an Action item, you MUST create an 'action' node AND you MUST create an edge of type 'IS_STATUS' pointing to a node with content 'OPEN'.
3. If a user describes an event with a date, create an edge of type 'HAS_DEADLINE' and put the exact ISO8601 timestamp in the metadata under the key 'date'. Calculate the date intelligently based on the Current Time.
4. If a user tracks a metric (e.g., "smoked 3 cigs"), create a 'concept' node for the metric ("cigs"), an 'action' node for the event ("smoked 3 cigs"), and a 'TRACKS_METRIC' edge between them, storing the value in metadata.
5. De-duplicate concepts where possible.

Example: "Need to finish my thesis by next Friday"
Nodes: 
  - {{"content": "Finish thesis", "node_type": "action"}}
  - {{"content": "OPEN", "node_type": "system_status"}}
Edges:
  - {{"source_content": "Finish thesis", "target_content": "OPEN", "edge_type": "IS_STATUS"}}
  - {{"source_content": "Finish thesis", "target_content": "Finish thesis", "edge_type": "HAS_DEADLINE", "metadata": {{"date": "2024-05-17T17:00:00Z"}}}}  <- (Target can be itself if it's a property of the node)
"""

    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_message}
        ],
        response_format=ExtractionResult,
    )
    
    return response.choices[0].message.parsed


async def process_brain_dump(session: AsyncSession, user_id: uuid.UUID, raw_message: str, current_time_iso: str, timezone: str):
    """The main entry point for the Cold Path Archiver."""
    
    logger.info(f"Starting Cold Path extraction for user {user_id}")
    
    # 1. Ensure system nodes exist
    await ensure_status_nodes(session, user_id)
    
    # 2. Run the LLM Extraction
    extraction: ExtractionResult = await run_extraction(raw_message, current_time_iso, timezone)
    
    logger.info(f"Extracted {len(extraction.nodes)} nodes and {len(extraction.edges)} edges.")
    
    # 3. Create the Nodes
    node_map = {} # Maps content string to UUID
    
    for enode in extraction.nodes:
        # TODO: In the future, we should generate embeddings here and do a semantic search 
        # to see if a similar node already exists (e.g. "Mom" vs "Mother") before creating a new one.
        # For MVP, we use exact string matching via get_or_create_node.
        db_node = await get_or_create_node(
            session=session,
            user_id=user_id,
            content=enode.content,
            node_type=enode.node_type
        )
        node_map[enode.content] = db_node.id
        
    # We must also ensure that targets that were implicitly referenced (like "OPEN") are in the map
    open_node, done_node = await ensure_status_nodes(session, user_id)
    node_map[STATUS_OPEN] = open_node.id
    node_map[STATUS_DONE] = done_node.id
        
    # 4. Create the Edges
    for edge in extraction.edges:
        source_id = node_map.get(edge.source_content)
        target_id = node_map.get(edge.target_content)
        
        if not source_id or not target_id:
            logger.warning(f"Skipping edge: Could not resolve source '{edge.source_content}' or target '{edge.target_content}'")
            continue
            
        await upsert_edge(
            session=session,
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge.edge_type,
            metadata=edge.metadata.model_dump(exclude_none=True) if edge.metadata else {}
        )
        
    # 5. Commit the transaction (writes to event_stream, graph_nodes, and graph_edges atomically)
    await session.commit()
    logger.info("Cold Path extraction completed and committed.")
