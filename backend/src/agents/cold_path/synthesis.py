import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from src.core.models import GraphNode, GraphEdge
from src.core.database import AsyncSessionLocal
from src.core.graph import get_or_create_node, upsert_edge
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

async def run_nightly_synthesis(user_id: uuid.UUID):
    """
    A periodic job that cleans up and synthesizes the graph.
    
    Responsibilities:
    1. Merge exact duplicate concepts.
    2. Prune old, completed nodes.
    3. Generate 'meta' insights (future feature using LLM clustering).
    """
    logger.info(f"Starting Nightly Synthesis for user {user_id}")
    
    async with AsyncSessionLocal() as session:
        # Example Synthesis: Find tasks marked DONE more than 7 days ago and soft-archive them
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        # 1. Find the 'DONE' system node
        stmt = select(GraphNode).where(
            and_(
                GraphNode.user_id == user_id,
                GraphNode.content == "DONE",
                GraphNode.node_type == "system_status"
            )
        )
        done_node = (await session.execute(stmt)).scalar_one_or_none()
        
        if done_node:
            # 2. Find all edges pointing to DONE created > 7 days ago
            edges_stmt = select(GraphEdge).where(
                and_(
                    GraphEdge.user_id == user_id,
                    GraphEdge.target_node_id == done_node.id,
                    GraphEdge.edge_type == "IS_STATUS",
                    GraphEdge.updated_at < seven_days_ago
                )
            )
            old_edges = (await session.execute(edges_stmt)).scalars().all()
            
            # 3. Soft archive the source nodes
            archived_count = 0
            for edge in old_edges:
                # We could update the node_type to 'archived_action'
                node_stmt = select(GraphNode).where(GraphNode.id == edge.source_node_id)
                source_node = (await session.execute(node_stmt)).scalar_one_or_none()
                if source_node and source_node.node_type == "action":
                    source_node.node_type = "archived_action"
                    archived_count += 1
            
            await session.commit()
            logger.info(f"Synthesizer archived {archived_count} old tasks.")
            
        logger.info("Nightly Synthesis complete.")

if __name__ == "__main__":
    # For testing the script directly
    import asyncio
    # Replace with a real user UUID for manual tests
    test_user = uuid.uuid4() 
    asyncio.run(run_nightly_synthesis(test_user))
