"""Graph memory database layer — uses production asyncpg pool."""

import uuid
from datetime import datetime, timedelta, timezone

import numpy as np

from src.db.supabase import get_pool
from src.telemetry.logger import get_logger

_log = get_logger("graph.db")


def _row_to_dict(row) -> dict:
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
        elif hasattr(v, "to_list"):
            d[k] = v.to_list()
    return d


def _rows_to_dicts(rows: list) -> list[dict]:
    return [_row_to_dict(r) for r in rows]


# --- Nodes ---


async def save_node(
    user_id: str,
    content: str,
    node_type: str | None = None,
    source_message_id: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    pool = get_pool()
    emb = np.array(embedding, dtype=np.float16) if embedding else None
    row = await pool.fetchrow(
        "INSERT INTO memory_nodes (user_id, content, node_type, embedding, source_message_id) "
        "VALUES ($1, $2, $3, $4::halfvec, $5) RETURNING *",
        user_id,
        content,
        node_type,
        emb,
        source_message_id,
    )
    return _row_to_dict(row)


async def get_node(node_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM memory_nodes WHERE id = $1", node_id)
    return _row_to_dict(row) if row else None


async def get_nodes_by_ids(node_ids: list[str]) -> list[dict]:
    if not node_ids:
        return []
    pool = get_pool()
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
    pool = get_pool()
    emb = np.array(embedding, dtype=np.float16)
    rows = await pool.fetch(
        "SELECT *, 1 - (embedding <=> $2::halfvec) AS score "
        "FROM memory_nodes WHERE user_id = $1 AND embedding IS NOT NULL "
        "AND 1 - (embedding <=> $2::halfvec) > $3 "
        "ORDER BY embedding <=> $2::halfvec LIMIT $4",
        user_id,
        emb,
        min_similarity,
        limit,
    )
    return _rows_to_dicts(rows)


async def get_recent_nodes(user_id: str, limit: int = 20) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE user_id = $1 "
        "ORDER BY last_activated_at DESC LIMIT $2",
        user_id,
        limit,
    )
    return _rows_to_dicts(rows)


async def update_node_embedding(node_id: str, embedding: list[float]) -> None:
    pool = get_pool()
    emb = np.array(embedding, dtype=np.float16)
    await pool.execute(
        "UPDATE memory_nodes SET embedding = $2::halfvec WHERE id = $1", node_id, emb
    )


async def update_nodes_last_activated(node_ids: list[str]) -> None:
    if not node_ids:
        return
    pool = get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET last_activated_at = now() WHERE id = ANY($1::uuid[])",
        node_ids,
    )


async def find_node_by_content(user_id: str, content: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM memory_nodes WHERE user_id = $1 AND lower(content) = lower($2) LIMIT 1",
        user_id,
        content,
    )
    return _row_to_dict(row) if row else None


async def get_all_nodes(user_id: str) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM memory_nodes WHERE user_id = $1 ORDER BY created_at",
        user_id,
    )
    return _rows_to_dicts(rows)


async def update_node_content(node_id: str, content: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET content = $2 WHERE id = $1", node_id, content
    )


async def update_node_status(node_id: str, status: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE memory_nodes SET status = $2 WHERE id = $1", node_id, status
    )


async def delete_node(node_id: str) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM memory_nodes WHERE id = $1", node_id)


# --- Edges (bi-temporal) ---


async def save_edge(
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    relation_type: str | None = None,
    source_message_id: str | None = None,
    strength: float = 1.0,
    decay_exempt: bool = False,
) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO memory_edges "
                "(user_id, from_node_id, to_node_id, relation_type, "
                "source_message_id, strength, decay_exempt) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                user_id,
                from_node_id,
                to_node_id,
                relation_type,
                source_message_id,
                strength,
                decay_exempt,
            )
            edge_id = row["id"]
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


async def invalidate_edge(edge_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE memory_edges SET valid_until = now() WHERE id = $1",
                edge_id,
            )
            await conn.execute("DELETE FROM node_neighbors WHERE edge_id = $1", edge_id)


async def get_edges_from(node_id: str, current_only: bool = True) -> list[dict]:
    pool = get_pool()
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


async def get_edges_between(
    node_ids: list[str], current_only: bool = True
) -> list[dict]:
    if not node_ids:
        return []
    pool = get_pool()
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


async def update_edge_strength(
    from_node_id: str, to_node_id: str, strength: float
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE memory_edges SET strength = $3 "
                "WHERE from_node_id = $1 AND to_node_id = $2 AND valid_until IS NULL",
                from_node_id,
                to_node_id,
                strength,
            )
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
    pool = get_pool()
    result = await pool.execute(
        "UPDATE memory_edges SET strength = strength * $2 "
        "WHERE user_id = $1 AND valid_until IS NULL "
        "AND decay_exempt = false AND strength > $3",
        user_id,
        factor,
        min_strength,
    )
    count = int(result.split()[-1]) if result else 0
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
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT id FROM memory_edges "
                "WHERE user_id = $1 AND valid_until IS NULL AND strength <= $2",
                user_id,
                min_strength,
            )
            if not rows:
                return 0
            edge_ids = [r["id"] for r in rows]
            await conn.execute(
                "UPDATE memory_edges SET valid_until = now() WHERE id = ANY($1::uuid[])",
                edge_ids,
            )
            await conn.execute(
                "DELETE FROM node_neighbors WHERE edge_id = ANY($1::uuid[])",
                edge_ids,
            )
    return len(edge_ids)


async def redirect_edges(from_old_id: str, to_new_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            outgoing = await conn.fetch(
                "SELECT * FROM memory_edges WHERE from_node_id = $1 AND valid_until IS NULL",
                from_old_id,
            )
            for e in outgoing:
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
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM node_neighbors WHERE edge_id IN "
                "(SELECT id FROM memory_edges WHERE user_id = $1)",
                user_id,
            )
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
    _log.info("graph.neighbor_cache_rebuilt", user_id=user_id, rows=count)
    return count


# --- Neighbor cache queries ---


async def get_neighbors(
    node_ids: list[str],
    exclude_ids: list[str] | None = None,
    limit: int = 30,
) -> list[dict]:
    if not node_ids:
        return []
    pool = get_pool()
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
    pool = get_pool()
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
    pool = get_pool()
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
    pool = get_pool()
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
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT "
        "(SELECT count(*) FROM memory_nodes WHERE user_id = $1) AS nodes, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NULL) AS current_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1 AND valid_until IS NOT NULL) AS invalidated_edges, "
        "(SELECT count(*) FROM memory_edges WHERE user_id = $1) AS total_edges",
        user_id,
    )
    return dict(row) if row else {}


# --- Reset ---


async def reset_graph(user_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM memory_edges WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM memory_nodes WHERE user_id = $1", user_id)
    _log.info("graph.reset", user_id=user_id)
