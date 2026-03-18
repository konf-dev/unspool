"""asyncpg database layer — all graph queries as Postgres SQL."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    async with _pool_lock:
        if _pool is None:
            from graph_lab_sql.src.config import PG_DSN

            _pool = await asyncpg.create_pool(
                dsn=PG_DSN,
                min_size=2,
                max_size=10,
                init=_init_connection,
                statement_cache_size=0,
            )
            logger.info("pg_pool_created")
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("pg_pool_closed")


async def run_schema() -> None:
    """Apply schema DDL using a raw connection (before pool creation).

    The pool's init callback registers the vector type codec, which requires
    the extension to already exist. So we run CREATE EXTENSION first via a
    plain connection, then close it. The pool can be created afterward.
    """
    from graph_lab_sql.src.config import PG_DSN

    conn = await asyncpg.connect(dsn=PG_DSN)
    try:
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text()
        await conn.execute(sql)
        logger.info("schema_applied")
    finally:
        await conn.close()


def _row_to_dict(row: asyncpg.Record | None) -> dict:
    if row is None:
        return {}
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, "tolist"):
            d[k] = v.tolist()
    return d


def _rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict]:
    return [_row_to_dict(r) for r in rows]


# --- Raw Stream ---


async def save_stream_entry(
    user_id: str,
    source: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    pool = await get_pool()
    import json

    row = await pool.fetchrow(
        "INSERT INTO raw_stream (user_id, source, content, metadata) "
        "VALUES ($1, $2, $3, $4) RETURNING *",
        user_id,
        source,
        content,
        json.dumps(metadata or {}),
    )
    return _row_to_dict(row)


async def get_recent_stream(user_id: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM raw_stream WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
        user_id,
        limit,
    )
    return _rows_to_dicts(rows)


async def get_session_stream(
    user_id: str, gap_hours: int = 4, limit: int = 20
) -> list[dict]:
    pool = await get_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=gap_hours)
    rows = await pool.fetch(
        "SELECT * FROM raw_stream WHERE user_id = $1 AND created_at > $2 "
        "ORDER BY created_at DESC LIMIT $3",
        user_id,
        cutoff,
        limit,
    )
    return _rows_to_dicts(rows)


# --- Nodes ---


async def save_node(
    user_id: str,
    content: str,
    node_type: str | None = None,
    source_stream_id: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    pool = await get_pool()
    import numpy as np

    emb = np.array(embedding, dtype=np.float32) if embedding else None
    row = await pool.fetchrow(
        "INSERT INTO memory_nodes (user_id, content, node_type, embedding, source_stream_id) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING *",
        user_id,
        content,
        node_type,
        emb,
        source_stream_id,
    )
    return _row_to_dict(row)


async def save_nodes_batch(user_id: str, nodes: list[dict]) -> list[dict]:
    pool = await get_pool()
    import numpy as np

    created = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for n in nodes:
                emb_raw = n.get("embedding")
                emb = np.array(emb_raw, dtype=np.float32) if emb_raw else None
                row = await conn.fetchrow(
                    "INSERT INTO memory_nodes (user_id, content, node_type, embedding, source_stream_id) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING *",
                    user_id,
                    n["content"],
                    n.get("node_type"),
                    emb,
                    n.get("source_stream_id"),
                )
                created.append(_row_to_dict(row))
    return created


async def get_node(node_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM memory_nodes WHERE id = $1", node_id)
    return _row_to_dict(row) if row else None


async def get_nodes_by_ids(node_ids: list[str]) -> list[dict]:
    if not node_ids:
        return []
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE id = ANY($1::uuid[])", node_ids
    )
    return _rows_to_dicts(rows)


async def search_nodes_semantic(
    user_id: str,
    embedding: list[float],
    limit: int = 15,
    min_similarity: float = 0.3,
) -> list[dict]:
    pool = await get_pool()
    import numpy as np

    emb = np.array(embedding, dtype=np.float32)
    rows = await pool.fetch(
        "SELECT *, 1 - (embedding <=> $2) AS score "
        "FROM memory_nodes WHERE user_id = $1 AND embedding IS NOT NULL "
        "AND 1 - (embedding <=> $2) > $3 "
        "ORDER BY embedding <=> $2 LIMIT $4",
        user_id,
        emb,
        min_similarity,
        limit,
    )
    return _rows_to_dicts(rows)


async def search_nodes_text(user_id: str, query: str, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE user_id = $1 "
        "AND lower(content) LIKE '%' || lower($2) || '%' LIMIT $3",
        user_id,
        query,
        limit,
    )
    return _rows_to_dicts(rows)


async def get_recent_nodes(user_id: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE user_id = $1 "
        "ORDER BY last_activated_at DESC LIMIT $2",
        user_id,
        limit,
    )
    return _rows_to_dicts(rows)


async def update_node_embedding(node_id: str, embedding: list[float]) -> None:
    pool = await get_pool()
    import numpy as np

    emb = np.array(embedding, dtype=np.float32)
    await pool.execute(
        "UPDATE memory_nodes SET embedding = $2 WHERE id = $1", node_id, emb
    )


async def update_nodes_last_activated(node_ids: list[str]) -> None:
    if not node_ids:
        return
    pool = await get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET last_activated_at = now() WHERE id = ANY($1::uuid[])",
        node_ids,
    )


async def find_node_by_content(user_id: str, content: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM memory_nodes WHERE user_id = $1 AND lower(content) = lower($2) LIMIT 1",
        user_id,
        content,
    )
    return _row_to_dict(row) if row else None


async def find_node_by_content_or_embedding(
    user_id: str,
    content: str,
    embedding: list[float] | None = None,
    similarity_threshold: float = 0.9,
) -> dict | None:
    exact = await find_node_by_content(user_id, content)
    if exact:
        return exact
    if embedding:
        results = await search_nodes_semantic(
            user_id, embedding, limit=1, min_similarity=similarity_threshold
        )
        if results:
            return results[0]
    return None


async def get_all_nodes(user_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE user_id = $1 ORDER BY created_at",
        user_id,
    )
    return _rows_to_dicts(rows)


async def update_node_content(node_id: str, content: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET content = $2 WHERE id = $1", node_id, content
    )


async def update_node_status(node_id: str, status: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET status = $2 WHERE id = $1", node_id, status
    )


async def delete_node(node_id: str) -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM memory_nodes WHERE id = $1", node_id)


# --- Edges (bi-temporal) ---


async def save_edge(
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    relation_type: str | None = None,
    source_stream_id: str | None = None,
    strength: float = 1.0,
    decay_exempt: bool = False,
) -> dict:
    """Create a new edge and populate the neighbor cache."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO memory_edges "
                "(user_id, from_node_id, to_node_id, relation_type, "
                "source_stream_id, strength, decay_exempt) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                user_id,
                from_node_id,
                to_node_id,
                relation_type,
                source_stream_id,
                strength,
                decay_exempt,
            )
            edge_id = row["id"]
            # Populate neighbor cache: outgoing from from_node, incoming to to_node
            await conn.execute(
                "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                "VALUES ($1, $2, $3, $4, $5, 'outgoing')",
                edge_id,
                from_node_id,
                to_node_id,
                relation_type,
                strength,
            )
            await conn.execute(
                "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                "VALUES ($1, $2, $3, $4, $5, 'incoming')",
                edge_id,
                to_node_id,
                from_node_id,
                relation_type,
                strength,
            )
    return _row_to_dict(row)


async def save_edges_batch(user_id: str, edges: list[dict]) -> list[dict]:
    pool = await get_pool()
    created = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for e in edges:
                row = await conn.fetchrow(
                    "INSERT INTO memory_edges "
                    "(user_id, from_node_id, to_node_id, relation_type, "
                    "source_stream_id, strength, decay_exempt) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                    user_id,
                    e["from_node_id"],
                    e["to_node_id"],
                    e.get("relation_type"),
                    e.get("source_stream_id"),
                    e.get("strength", 1.0),
                    e.get("decay_exempt", False),
                )
                edge_id = row["id"]
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'outgoing')",
                    edge_id,
                    e["from_node_id"],
                    e["to_node_id"],
                    e.get("relation_type"),
                    e.get("strength", 1.0),
                )
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'incoming')",
                    edge_id,
                    e["to_node_id"],
                    e["from_node_id"],
                    e.get("relation_type"),
                    e.get("strength", 1.0),
                )
                created.append(_row_to_dict(row))
    return created


async def invalidate_edge(edge_id: str) -> None:
    """Set valid_until=now() on an edge and remove from neighbor cache."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE memory_edges SET valid_until = now() WHERE id = $1",
                edge_id,
            )
            await conn.execute("DELETE FROM node_neighbors WHERE edge_id = $1", edge_id)


async def get_edges_from(node_id: str, current_only: bool = True) -> list[dict]:
    """Get edges originating from a node. current_only filters to valid_until IS NULL."""
    pool = await get_pool()
    if current_only:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges WHERE from_node_id = $1 AND valid_until IS NULL",
            node_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges WHERE from_node_id = $1", node_id
        )
    return _rows_to_dicts(rows)


async def get_edges_to(node_id: str, current_only: bool = True) -> list[dict]:
    pool = await get_pool()
    if current_only:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges WHERE to_node_id = $1 AND valid_until IS NULL",
            node_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges WHERE to_node_id = $1", node_id
        )
    return _rows_to_dicts(rows)


async def get_edges_between(
    node_ids: list[str], current_only: bool = True
) -> list[dict]:
    if not node_ids:
        return []
    pool = await get_pool()
    if current_only:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges "
            "WHERE from_node_id = ANY($1::uuid[]) AND to_node_id = ANY($1::uuid[]) "
            "AND valid_until IS NULL",
            node_ids,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_edges "
            "WHERE from_node_id = ANY($1::uuid[]) AND to_node_id = ANY($1::uuid[])",
            node_ids,
        )
    return _rows_to_dicts(rows)


async def get_edge_history(from_node_id: str, to_node_id: str) -> list[dict]:
    """Get all edges (current + invalidated) between two nodes, ordered by valid_from."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_edges "
        "WHERE from_node_id = $1 AND to_node_id = $2 "
        "ORDER BY valid_from",
        from_node_id,
        to_node_id,
    )
    return _rows_to_dicts(rows)


async def update_edge_strength(
    from_node_id: str, to_node_id: str, strength: float
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE memory_edges SET strength = $3 "
                "WHERE from_node_id = $1 AND to_node_id = $2 AND valid_until IS NULL",
                from_node_id,
                to_node_id,
                strength,
            )
            # Sync neighbor cache
            await conn.execute(
                "UPDATE node_neighbors SET strength = $3 "
                "FROM memory_edges me "
                "WHERE node_neighbors.edge_id = me.id "
                "AND me.from_node_id = $1 AND me.to_node_id = $2 "
                "AND me.valid_until IS NULL",
                from_node_id,
                to_node_id,
                strength,
            )


async def decay_edges(user_id: str, factor: float, min_strength: float) -> int:
    """Decay all current non-exempt edges. Returns count of edges decayed."""
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE memory_edges SET strength = strength * $2 "
        "WHERE user_id = $1 AND valid_until IS NULL "
        "AND decay_exempt = false AND strength > $3",
        user_id,
        factor,
        min_strength,
    )
    # Parse "UPDATE N" result
    count = int(result.split()[-1]) if result else 0

    # Batch-sync neighbor cache strengths
    if count > 0:
        await pool.execute(
            "UPDATE node_neighbors SET strength = me.strength "
            "FROM memory_edges me "
            "WHERE node_neighbors.edge_id = me.id "
            "AND me.user_id = $1 AND me.valid_until IS NULL",
            user_id,
        )
    return count


async def prune_weak_edges(user_id: str, min_strength: float) -> int:
    """Invalidate (not delete) edges below threshold. Returns count."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Find edges to invalidate
            rows = await conn.fetch(
                "SELECT id FROM memory_edges "
                "WHERE user_id = $1 AND valid_until IS NULL AND strength <= $2",
                user_id,
                min_strength,
            )
            if not rows:
                return 0
            edge_ids = [r["id"] for r in rows]
            # Invalidate edges
            await conn.execute(
                "UPDATE memory_edges SET valid_until = now() WHERE id = ANY($1::uuid[])",
                edge_ids,
            )
            # Remove from neighbor cache
            await conn.execute(
                "DELETE FROM node_neighbors WHERE edge_id = ANY($1::uuid[])",
                edge_ids,
            )
    return len(edge_ids)


async def redirect_edges(from_old_id: str, to_new_id: str) -> None:
    """Redirect all current edges from one node to another (for merging).

    Invalidates old edges and creates new ones pointing to the new node.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Edges where old node is the source (from_node_id)
            outgoing = await conn.fetch(
                "SELECT * FROM memory_edges WHERE from_node_id = $1 AND valid_until IS NULL",
                from_old_id,
            )
            for e in outgoing:
                # Invalidate old
                await conn.execute(
                    "UPDATE memory_edges SET valid_until = now() WHERE id = $1",
                    e["id"],
                )
                await conn.execute(
                    "DELETE FROM node_neighbors WHERE edge_id = $1", e["id"]
                )
                # Create new edge from new_node to same target
                new_row = await conn.fetchrow(
                    "INSERT INTO memory_edges "
                    "(user_id, from_node_id, to_node_id, relation_type, strength, decay_exempt) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                    e["user_id"],
                    to_new_id,
                    e["to_node_id"],
                    e["relation_type"],
                    e["strength"],
                    e["decay_exempt"],
                )
                new_id = new_row["id"]
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'outgoing')",
                    new_id,
                    to_new_id,
                    e["to_node_id"],
                    e["relation_type"],
                    e["strength"],
                )
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'incoming')",
                    new_id,
                    e["to_node_id"],
                    to_new_id,
                    e["relation_type"],
                    e["strength"],
                )

            # Edges where old node is the target (to_node_id)
            incoming = await conn.fetch(
                "SELECT * FROM memory_edges WHERE to_node_id = $1 AND valid_until IS NULL",
                from_old_id,
            )
            for e in incoming:
                await conn.execute(
                    "UPDATE memory_edges SET valid_until = now() WHERE id = $1",
                    e["id"],
                )
                await conn.execute(
                    "DELETE FROM node_neighbors WHERE edge_id = $1", e["id"]
                )
                new_row = await conn.fetchrow(
                    "INSERT INTO memory_edges "
                    "(user_id, from_node_id, to_node_id, relation_type, strength, decay_exempt) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                    e["user_id"],
                    e["from_node_id"],
                    to_new_id,
                    e["relation_type"],
                    e["strength"],
                    e["decay_exempt"],
                )
                new_id = new_row["id"]
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'outgoing')",
                    new_id,
                    e["from_node_id"],
                    to_new_id,
                    e["relation_type"],
                    e["strength"],
                )
                await conn.execute(
                    "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                    "VALUES ($1, $2, $3, $4, $5, 'incoming')",
                    new_id,
                    to_new_id,
                    e["from_node_id"],
                    e["relation_type"],
                    e["strength"],
                )


async def rebuild_neighbor_cache(user_id: str) -> int:
    """Full rebuild of neighbor cache for a user. Returns rows inserted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Delete existing cache for this user's edges
            await conn.execute(
                "DELETE FROM node_neighbors WHERE edge_id IN "
                "(SELECT id FROM memory_edges WHERE user_id = $1)",
                user_id,
            )
            # Rebuild from current edges only
            result = await conn.execute(
                "INSERT INTO node_neighbors (edge_id, node_id, neighbor_id, relation_type, strength, direction) "
                "SELECT id, from_node_id, to_node_id, relation_type, strength, 'outgoing' "
                "FROM memory_edges WHERE user_id = $1 AND valid_until IS NULL "
                "UNION ALL "
                "SELECT id, to_node_id, from_node_id, relation_type, strength, 'incoming' "
                "FROM memory_edges WHERE user_id = $1 AND valid_until IS NULL",
                user_id,
            )
    count = int(result.split()[-1]) if result else 0
    logger.info("neighbor_cache_rebuilt", user_id=user_id, rows=count)
    return count


# --- Neighbor cache queries (used by triggers) ---


async def get_neighbors(
    node_ids: list[str],
    exclude_ids: list[str] | None = None,
    limit: int = 30,
) -> list[dict]:
    """Get neighbors of nodes via cache. Excludes already-known nodes."""
    if not node_ids:
        return []
    pool = await get_pool()
    exclude = exclude_ids or []
    rows = await pool.fetch(
        "SELECT DISTINCT nn.neighbor_id, mn.content, mn.last_activated_at "
        "FROM node_neighbors nn "
        "JOIN memory_nodes mn ON mn.id = nn.neighbor_id "
        "WHERE nn.node_id = ANY($1::uuid[]) AND nn.strength > 0.01 "
        "AND nn.neighbor_id != ALL($2::uuid[]) "
        "LIMIT $3",
        node_ids,
        exclude,
        limit,
    )
    return _rows_to_dicts(rows)


async def find_nodes_by_status_neighbor(
    user_id: str,
    status_content: str,
    direction: str = "incoming",
) -> list[dict]:
    """Find nodes connected to a status node via neighbor cache.

    direction='incoming' means: find nodes that have the status node as an
    outgoing neighbor (i.e., task → "not done"). We want the task nodes,
    so we look for entries where neighbor_id points to the status node.
    """
    pool = await get_pool()
    if direction == "incoming":
        rows = await pool.fetch(
            "SELECT DISTINCT mn.* FROM node_neighbors nn "
            "JOIN memory_nodes status ON status.id = nn.neighbor_id "
            "JOIN memory_nodes mn ON mn.id = nn.node_id "
            "WHERE status.user_id = $1 AND lower(status.content) = lower($2) "
            "AND nn.direction = 'outgoing' AND nn.strength > 0.01",
            user_id,
            status_content,
        )
    else:
        rows = await pool.fetch(
            "SELECT DISTINCT mn.* FROM node_neighbors nn "
            "JOIN memory_nodes status ON status.id = nn.neighbor_id "
            "JOIN memory_nodes mn ON mn.id = nn.node_id "
            "WHERE status.user_id = $1 AND lower(status.content) = lower($2) "
            "AND nn.direction = 'incoming' AND nn.strength > 0.01",
            user_id,
            status_content,
        )
    return _rows_to_dicts(rows)


async def find_recently_surfaced(user_id: str, hours: int = 24) -> list[str]:
    """Find node IDs that were surfaced within the time window."""
    pool = await get_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await pool.fetch(
        "SELECT DISTINCT nn.node_id FROM node_neighbors nn "
        "JOIN memory_nodes status ON status.id = nn.neighbor_id "
        "JOIN memory_edges me ON me.id = nn.edge_id "
        "WHERE status.user_id = $1 AND lower(status.content) = 'surfaced' "
        "AND nn.direction = 'outgoing' "
        "AND me.valid_from > $2",
        user_id,
        cutoff,
    )
    return [str(r["node_id"]) for r in rows]


async def find_temporal_nodes(user_id: str) -> list[dict]:
    """Find date nodes within the temporal window (7 days back, 2 days forward)
    and their connected nodes, using SQL instead of Python loops."""
    pool = await get_pool()
    rows = await pool.fetch(
        "WITH date_nodes AS ( "
        "  SELECT id FROM memory_nodes "
        "  WHERE user_id = $1 "
        "    AND content ~ '^\\d{4}-\\d{2}-\\d{2}$' "
        "    AND content::date BETWEEN CURRENT_DATE - 7 AND CURRENT_DATE + 2 "
        ") "
        "SELECT DISTINCT mn.* FROM ( "
        "  SELECT nn.node_id AS id FROM date_nodes dn "
        "  JOIN node_neighbors nn ON nn.neighbor_id = dn.id AND nn.direction = 'outgoing' "
        "  UNION "
        "  SELECT id FROM date_nodes "
        ") matched "
        "JOIN memory_nodes mn ON mn.id = matched.id",
        user_id,
    )
    return _rows_to_dicts(rows)


# --- Stats ---


async def get_graph_stats(user_id: str) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT "
        "(SELECT count(*) FROM memory_nodes WHERE user_id = $1) AS nodes, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NULL) AS current_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NOT NULL) AS invalidated_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1) AS total_edges, "
        "(SELECT count(*) FROM raw_stream WHERE user_id = $1) AS stream_entries, "
        "(SELECT count(*) FROM node_neighbors nn "
        "  JOIN memory_edges me ON me.id = nn.edge_id WHERE me.user_id = $1) AS cache_rows",
        user_id,
    )
    d = dict(row) if row else {}
    # Compatibility alias: dashboard expects "edges" key
    if "current_edges" in d:
        d["edges"] = d["current_edges"]
    return d


async def get_temporal_stats(user_id: str) -> dict:
    """Get bi-temporal edge statistics."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1) AS total_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NULL) AS current_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NOT NULL) AS invalidated_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND decay_exempt = true) AS decay_exempt_edges",
        user_id,
    )
    return dict(row) if row else {}


# --- Reset ---


async def reset_graph(user_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Neighbor cache is cascade-deleted via edge FK
            await conn.execute("DELETE FROM memory_edges WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM memory_nodes WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM raw_stream WHERE user_id = $1", user_id)
    logger.info("graph_reset", user_id=user_id)
