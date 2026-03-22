import logging
from typing import Dict, Any, List
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.core.graph import search_nodes_semantic
from src.core.models import GraphNode, GraphEdge
from langchain_core.tools import tool
from src.core.database import AsyncSessionLocal
from src.core.config import settings
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client to generate embeddings for semantic search
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def get_embedding(text: str) -> list[float]:
    response = await client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


@tool
async def query_graph(user_id: str, semantic_query: str, edge_type_filter: str = None) -> List[Dict[str, Any]]:
    """
    Searches the user's memory graph for nodes matching the query.
    
    Args:
        user_id: The UUID of the current user.
        semantic_query: The concept or task to search for (e.g., 'Mom', 'Thesis deadlines').
        edge_type_filter: Optional. If provided, only returns nodes that have this specific edge type (e.g. 'HAS_DEADLINE', 'IS_STATUS').
    """
    try:
        user_uuid = uuid.UUID(user_id)
        embedding = await get_embedding(semantic_query)
        
        async with AsyncSessionLocal() as session:
            nodes = await search_nodes_semantic(session, user_uuid, embedding, limit=5)
            
            results = []
            for node in nodes:
                # If filter is applied, verify the node has an edge of that type
                if edge_type_filter:
                    stmt = select(GraphEdge).where(
                        and_(
                            GraphEdge.user_id == user_uuid,
                            GraphEdge.source_node_id == node.id,
                            GraphEdge.edge_type == edge_type_filter
                        )
                    )
                    edges = (await session.execute(stmt)).scalars().all()
                    if not edges:
                        continue # Skip this node if it doesn't have the required edge
                        
                results.append({
                    "id": str(node.id),
                    "content": node.content,
                    "type": node.node_type
                })
                
            return results
    except Exception as e:
        logger.error(f"Error querying graph: {e}")
        return [{"error": str(e)}]


@tool
async def mutate_graph_status(user_id: str, node_id: str, new_status: str) -> str:
    """
    Updates the status of a specific node in the graph. You MUST know the exact node_id first by using query_graph.
    
    Args:
        user_id: The UUID of the current user.
        node_id: The UUID of the node to update.
        new_status: The new status (must be 'OPEN' or 'DONE').
    """
    from src.core.graph import upsert_edge, get_or_create_node
    
    if new_status not in ["OPEN", "DONE"]:
        return "Error: new_status must be 'OPEN' or 'DONE'."
        
    try:
        user_uuid = uuid.UUID(user_id)
        node_uuid = uuid.UUID(node_id)
        
        async with AsyncSessionLocal() as session:
            # 1. Ensure the target status node exists
            status_node = await get_or_create_node(session, user_uuid, new_status, "system_status")
            
            # 2. Upsert the IS_STATUS edge to point to this status node
            await upsert_edge(
                session=session,
                user_id=user_uuid,
                source_id=node_uuid,
                target_id=status_node.id,
                edge_type="IS_STATUS"
            )
            
            await session.commit()
            return f"Successfully updated node status to {new_status}."
            
    except Exception as e:
        logger.error(f"Error mutating graph: {e}")
        return f"Error mutating graph: {str(e)}"
