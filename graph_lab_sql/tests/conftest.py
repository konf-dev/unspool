"""Test fixtures — local Postgres with schema setup and per-test cleanup."""

import os

import pytest
import pytest_asyncio

# Set test env vars before any graph_lab_sql imports
os.environ.setdefault(
    "PG_DSN", "postgresql://graph_lab:graph_lab@localhost:5433/graph_lab_test"
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

_schema_applied = False


async def _ensure_schema():
    """Create test DB and apply schema (idempotent)."""
    global _schema_applied
    if _schema_applied:
        return

    import asyncpg

    dsn = os.environ["PG_DSN"]
    base_dsn = dsn.rsplit("/", 1)[0] + "/graph_lab"
    test_db = dsn.rsplit("/", 1)[1]

    conn = await asyncpg.connect(base_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", test_db
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{test_db}"')
    finally:
        await conn.close()

    conn = await asyncpg.connect(dsn)
    try:
        from pathlib import Path

        schema_sql = (Path(__file__).parent.parent / "src" / "schema.sql").read_text()
        await conn.execute(schema_sql)
    finally:
        await conn.close()

    _schema_applied = True


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Ensure schema exists, get pool, truncate tables between tests."""
    await _ensure_schema()

    from graph_lab_sql.src import db

    pool = await db.get_pool()
    await pool.execute(
        "TRUNCATE node_neighbors, memory_edges, memory_nodes, raw_stream CASCADE"
    )
    yield
    await db.close()


@pytest.fixture
def user_id():
    return "00000000-0000-0000-0000-000000000001"
