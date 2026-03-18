"""Create graph_lab schema and tables in SurrealDB."""

import asyncio

import structlog
from graph_lab.src.config import SURREALDB_PASS, SURREALDB_URL, SURREALDB_USER
from surrealdb import AsyncSurreal

logger = structlog.get_logger()

SCHEMA_STATEMENTS = [
    # Raw stream table
    "DEFINE TABLE raw_stream SCHEMAFULL",
    "DEFINE FIELD user_id ON raw_stream TYPE string",
    "DEFINE FIELD source ON raw_stream TYPE string "
    'ASSERT $value IN ["user", "unspool", "calendar", "system"]',
    "DEFINE FIELD content ON raw_stream TYPE string",
    "DEFINE FIELD metadata ON raw_stream TYPE option<object>",
    "DEFINE FIELD created_at ON raw_stream TYPE datetime DEFAULT time::now()",
    "DEFINE INDEX idx_stream_user_time ON raw_stream FIELDS user_id, created_at",
    # Node table
    "DEFINE TABLE node SCHEMAFULL",
    "DEFINE FIELD user_id ON node TYPE string",
    "DEFINE FIELD content ON node TYPE string",
    "DEFINE FIELD embedding ON node TYPE option<array<float>>",
    "DEFINE FIELD source_stream ON node TYPE option<record<raw_stream>>",
    "DEFINE FIELD created_at ON node TYPE datetime DEFAULT time::now()",
    "DEFINE FIELD last_activated_at ON node TYPE datetime DEFAULT time::now()",
    "DEFINE INDEX idx_node_user ON node FIELDS user_id",
    "DEFINE INDEX idx_node_activated ON node FIELDS user_id, last_activated_at",
    "DEFINE INDEX idx_node_embedding ON node FIELDS embedding HNSW DIMENSION 768 DIST COSINE",
    # Note: FULLTEXT index removed — SurrealDB 3.0 Cloud has a broken default
    # analyzer. Using string::lowercase(content) CONTAINS for text search instead.
    # Edge table (relation)
    "DEFINE TABLE edge TYPE RELATION IN node OUT node SCHEMAFULL",
    "DEFINE FIELD user_id ON edge TYPE string",
    "DEFINE FIELD source_stream ON edge TYPE option<record<raw_stream>>",
    "DEFINE FIELD strength ON edge TYPE float DEFAULT 1.0",
    "DEFINE FIELD created_at ON edge TYPE datetime DEFAULT time::now()",
    "DEFINE FIELD last_traversed_at ON edge TYPE datetime DEFAULT time::now()",
]


async def run_migration() -> None:
    logger.info("migration_start", url=SURREALDB_URL)
    client = AsyncSurreal(SURREALDB_URL)
    try:
        await client.connect()
        await client.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})
        await client.use("unspool", "graph_lab")

        for stmt in SCHEMA_STATEMENTS:
            try:
                await client.query(stmt)
                logger.info("migration_statement_ok", statement=stmt[:60])
            except Exception as e:
                logger.warning("migration_statement_error", statement=stmt[:60], error=str(e))

        logger.info("migration_complete")
    finally:
        await client.close()


async def drop_all() -> None:
    """Drop all data (use with care)."""
    logger.warning("dropping_all_data")
    client = AsyncSurreal(SURREALDB_URL)
    try:
        await client.connect()
        await client.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})
        await client.use("unspool", "graph_lab")
        await client.query("DELETE edge")
        await client.query("DELETE node")
        await client.query("DELETE raw_stream")
        logger.info("all_data_dropped")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
