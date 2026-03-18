import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from graph_lab.src.config import SURREALDB_PASS, SURREALDB_URL, SURREALDB_USER
from surrealdb import AsyncSurreal, RecordID

logger = structlog.get_logger()

_client = None
_client_lock = asyncio.Lock()


async def get_client():
    global _client
    async with _client_lock:
        if _client is None:
            c = AsyncSurreal(SURREALDB_URL)
            await c.connect()
            await c.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})
            await c.use("unspool", "graph_lab")
            _client = c
    return _client


async def close():
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# --- Normalization ---


def _normalize(val):
    """Recursively convert RecordID and datetime objects to strings."""
    if isinstance(val, RecordID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _normalize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_normalize(v) for v in val]
    return val


def _rid(string_id: str) -> RecordID:
    """Convert 'table:key' string back to RecordID for SurrealDB queries."""
    if isinstance(string_id, RecordID):
        return string_id
    parts = string_id.split(":", 1)
    if len(parts) == 2:
        return RecordID(parts[0], parts[1])
    return RecordID("node", string_id)


def _rids(string_ids: list[str]) -> list[RecordID]:
    """Convert list of string IDs to RecordIDs."""
    return [_rid(sid) for sid in string_ids]


def _rows(result) -> list[dict]:
    """Extract rows from SurrealDB query result, normalized."""
    if isinstance(result, list):
        return [_normalize(item) for item in result if isinstance(item, dict)]
    return []


def _first(result) -> dict:
    """Extract first record from SurrealDB query result."""
    rows = _rows(result)
    return rows[0] if rows else {}


def _count(result) -> int:
    rows = _rows(result)
    if rows and isinstance(rows[0], dict):
        return rows[0].get("c", 0)
    return 0


def _flatten_traversal(result) -> list[dict]:
    """Flatten traversal results into a flat node list."""
    nodes: list[dict] = []
    seen: set[str] = set()
    raw = _rows(result)

    for record in raw:
        if not isinstance(record, dict):
            continue
        for key, val in record.items():
            if key == "id":
                continue
            items = val if isinstance(val, list) else [val]
            for item in items:
                if isinstance(item, dict) and "id" in item:
                    nid = str(item["id"])
                    if nid not in seen:
                        seen.add(nid)
                        nodes.append(_normalize(item))
    return nodes


# --- Raw Stream ---


async def save_stream_entry(
    user_id: str,
    source: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    db = await get_client()
    result = await db.query(
        "CREATE raw_stream SET user_id = $uid, source = $source, "
        "content = $content, metadata = $meta, created_at = time::now()",
        {"uid": user_id, "source": source, "content": content, "meta": metadata or {}},
    )
    return _first(result)


async def get_recent_stream(user_id: str, limit: int = 20) -> list[dict]:
    db = await get_client()
    result = await db.query(
        "SELECT * FROM raw_stream WHERE user_id = $uid ORDER BY created_at DESC LIMIT $limit",
        {"uid": user_id, "limit": limit},
    )
    return _rows(result)


async def get_session_stream(user_id: str, gap_hours: int = 4, limit: int = 20) -> list[dict]:
    """Get recent stream entries, split by session gap."""
    db = await get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=gap_hours)
    result = await db.query(
        "SELECT * FROM raw_stream WHERE user_id = $uid AND created_at > $cutoff "
        "ORDER BY created_at DESC LIMIT $limit",
        {"uid": user_id, "limit": limit, "cutoff": cutoff.isoformat()},
    )
    return _rows(result)


# --- Nodes ---


async def save_node(
    user_id: str,
    content: str,
    source_stream_id: str | None = None,
    embedding: list[float] | None = None,
) -> dict:
    db = await get_client()
    result = await db.query(
        "CREATE node SET user_id = $uid, content = $content, "
        "source_stream = $source, embedding = $emb, "
        "created_at = time::now(), last_activated_at = time::now()",
        {
            "uid": user_id,
            "content": content,
            "source": _rid(source_stream_id) if source_stream_id else None,
            "emb": embedding,
        },
    )
    return _first(result)


async def save_nodes_batch(user_id: str, nodes: list[dict]) -> list[dict]:
    db = await get_client()
    created = []
    for n in nodes:
        ssid = n.get("source_stream_id")
        result = await db.query(
            "CREATE node SET user_id = $uid, content = $content, "
            "source_stream = $source, embedding = $emb, "
            "created_at = time::now(), last_activated_at = time::now()",
            {
                "uid": user_id,
                "content": n["content"],
                "source": _rid(ssid) if ssid else None,
                "emb": n.get("embedding"),
            },
        )
        created.append(_first(result))
    return created


async def get_node(node_id: str) -> dict | None:
    db = await get_client()
    result = await db.query("SELECT * FROM $id", {"id": _rid(node_id)})
    rows = _rows(result)
    return rows[0] if rows else None


async def get_nodes_by_ids(node_ids: list[str]) -> list[dict]:
    if not node_ids:
        return []
    db = await get_client()
    result = await db.query(
        "SELECT * FROM node WHERE id IN $ids",
        {"ids": _rids(node_ids)},
    )
    return _rows(result)


async def search_nodes_semantic(
    user_id: str,
    embedding: list[float],
    limit: int = 15,
    min_similarity: float = 0.3,
) -> list[dict]:
    db = await get_client()
    result = await db.query(
        "SELECT *, vector::similarity::cosine(embedding, $vec) AS score "
        f"FROM node WHERE user_id = $uid AND embedding <|{limit}|> $vec",
        {"uid": user_id, "vec": embedding},
    )
    rows = _rows(result)
    return [r for r in rows if r.get("score", 0) >= min_similarity]


async def search_nodes_text(user_id: str, query: str, limit: int = 10) -> list[dict]:
    """Simple text search using string::contains."""
    db = await get_client()
    result = await db.query(
        "SELECT * FROM node WHERE user_id = $uid "
        "AND string::lowercase(content) CONTAINS string::lowercase($query) "
        "LIMIT $limit",
        {"uid": user_id, "query": query, "limit": limit},
    )
    return _rows(result)


async def get_recent_nodes(user_id: str, limit: int = 20) -> list[dict]:
    db = await get_client()
    result = await db.query(
        "SELECT * FROM node WHERE user_id = $uid ORDER BY last_activated_at DESC LIMIT $limit",
        {"uid": user_id, "limit": limit},
    )
    return _rows(result)


async def update_node_embedding(node_id: str, embedding: list[float]) -> None:
    db = await get_client()
    await db.query(
        "UPDATE $id SET embedding = $emb",
        {"id": _rid(node_id), "emb": embedding},
    )


async def update_nodes_last_activated(node_ids: list[str]) -> None:
    if not node_ids:
        return
    db = await get_client()
    await db.query(
        "UPDATE node SET last_activated_at = time::now() WHERE id IN $ids",
        {"ids": _rids(node_ids)},
    )


async def find_node_by_content(user_id: str, content: str) -> dict | None:
    """Exact case-insensitive match."""
    db = await get_client()
    result = await db.query(
        "SELECT * FROM node WHERE user_id = $uid "
        "AND string::lowercase(content) = string::lowercase($content) LIMIT 1",
        {"uid": user_id, "content": content},
    )
    rows = _rows(result)
    return rows[0] if rows else None


async def find_node_by_content_or_embedding(
    user_id: str,
    content: str,
    embedding: list[float] | None = None,
    similarity_threshold: float = 0.9,
) -> dict | None:
    """Exact match first, then embedding similarity if available."""
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
    db = await get_client()
    result = await db.query(
        "SELECT * FROM node WHERE user_id = $uid ORDER BY created_at",
        {"uid": user_id},
    )
    return _rows(result)


async def update_node_content(node_id: str, content: str) -> None:
    db = await get_client()
    await db.query(
        "UPDATE $id SET content = $content",
        {"id": _rid(node_id), "content": content},
    )


async def delete_node(node_id: str) -> None:
    db = await get_client()
    await db.query("DELETE $id", {"id": _rid(node_id)})


# --- Edges ---


async def save_edge(
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    source_stream_id: str | None = None,
    strength: float = 1.0,
) -> dict:
    db = await get_client()
    result = await db.query(
        "RELATE $from->edge->$to SET user_id = $uid, "
        "source_stream = $source, strength = $strength, "
        "created_at = time::now(), last_traversed_at = time::now()",
        {
            "from": _rid(from_node_id),
            "to": _rid(to_node_id),
            "uid": user_id,
            "source": _rid(source_stream_id) if source_stream_id else None,
            "strength": strength,
        },
    )
    return _first(result)


async def save_edges_batch(user_id: str, edges: list[dict]) -> list[dict]:
    db = await get_client()
    created = []
    for e in edges:
        result = await db.query(
            "RELATE $from->edge->$to SET user_id = $uid, "
            "source_stream = $source, strength = $strength, "
            "created_at = time::now(), last_traversed_at = time::now()",
            {
                "from": _rid(e["from_node_id"]),
                "to": _rid(e["to_node_id"]),
                "uid": user_id,
                "source": _rid(e["source_stream_id"]) if e.get("source_stream_id") else None,
                "strength": e.get("strength", 1.0),
            },
        )
        created.append(_first(result))
    return created


async def get_edges_from(node_id: str) -> list[dict]:
    db = await get_client()
    result = await db.query(
        "SELECT * FROM edge WHERE in = $id",
        {"id": _rid(node_id)},
    )
    return _rows(result)


async def get_edges_to(node_id: str) -> list[dict]:
    db = await get_client()
    result = await db.query(
        "SELECT * FROM edge WHERE out = $id",
        {"id": _rid(node_id)},
    )
    return _rows(result)


async def get_edges_between(node_ids: list[str]) -> list[dict]:
    """All edges where both endpoints are in the given set."""
    if not node_ids:
        return []
    db = await get_client()
    result = await db.query(
        "SELECT * FROM edge WHERE in IN $ids AND out IN $ids",
        {"ids": _rids(node_ids)},
    )
    return _rows(result)


async def traverse_from(node_id: str, hops: int = 1, direction: str = "both") -> list[dict]:
    """Walk N hops from a node. Returns connected nodes."""
    db = await get_client()
    if hops == 1:
        if direction == "outgoing":
            query = "SELECT ->edge->node.* AS nodes FROM $id"
        elif direction == "incoming":
            query = "SELECT <-edge<-node.* AS nodes FROM $id"
        else:
            query = "SELECT ->edge->node.* AS outgoing, <-edge<-node.* AS incoming FROM $id"
    elif hops == 2:
        if direction == "outgoing":
            query = "SELECT ->edge->node.* AS hop1, ->edge->node->edge->node.* AS hop2 FROM $id"
        elif direction == "incoming":
            query = "SELECT <-edge<-node.* AS hop1, <-edge<-node<-edge<-node.* AS hop2 FROM $id"
        else:
            query = (
                "SELECT ->edge->node.* AS out1, <-edge<-node.* AS in1, "
                "->edge->node->edge->node.* AS out2, "
                "<-edge<-node<-edge<-node.* AS in2 FROM $id"
            )
    else:
        query = "SELECT ->edge->node.* AS nodes FROM $id"

    result = await db.query(query, {"id": _rid(node_id)})
    return _flatten_traversal(result)


async def traverse_from_many(user_id: str, node_ids: list[str], hops: int = 1) -> list[dict]:
    """Walk from multiple start nodes, deduplicate results."""
    seen: set[str] = set()
    all_nodes: list[dict] = []
    for nid in node_ids:
        walked = await traverse_from(nid, hops=hops)
        for n in walked:
            rid = str(n.get("id", ""))
            if rid and rid not in seen:
                seen.add(rid)
                all_nodes.append(n)
    return all_nodes


async def find_nodes_connected_to(
    user_id: str, content: str, direction: str = "incoming"
) -> list[dict]:
    """Find all nodes connected to a node with the given content."""
    target = await find_node_by_content(user_id, content)
    if not target:
        return []
    target_id = target["id"]
    db = await get_client()
    rid = _rid(target_id)
    if direction == "incoming":
        result = await db.query(
            "SELECT <-edge<-node.* AS nodes FROM $id",
            {"id": rid},
        )
    elif direction == "outgoing":
        result = await db.query(
            "SELECT ->edge->node.* AS nodes FROM $id",
            {"id": rid},
        )
    else:
        result = await db.query(
            "SELECT ->edge->node.* AS outgoing, <-edge<-node.* AS incoming FROM $id",
            {"id": rid},
        )
    return _flatten_traversal(result)


async def update_edge_strength(from_node_id: str, to_node_id: str, strength: float) -> None:
    db = await get_client()
    await db.query(
        "UPDATE edge SET strength = $strength WHERE in = $from AND out = $to",
        {"from": _rid(from_node_id), "to": _rid(to_node_id), "strength": strength},
    )


async def decay_edges(user_id: str, factor: float, min_strength: float) -> int:
    db = await get_client()
    result = await db.query(
        "UPDATE edge SET strength = strength * $factor WHERE user_id = $uid AND strength > $min",
        {"uid": user_id, "factor": factor, "min": min_strength},
    )
    return len(_rows(result))


async def prune_weak_edges(user_id: str, min_strength: float) -> int:
    db = await get_client()
    result = await db.query(
        "DELETE edge WHERE user_id = $uid AND strength <= $min RETURN BEFORE",
        {"uid": user_id, "min": min_strength},
    )
    return len(_rows(result))


async def redirect_edges(from_old_id: str, to_new_id: str) -> None:
    """Redirect all edges from one node to another (for merging)."""
    db = await get_client()
    old_rid = _rid(from_old_id)
    new_rid = _rid(to_new_id)
    incoming = await db.query("SELECT * FROM edge WHERE out = $old", {"old": old_rid})
    for e in _rows(incoming):
        await db.query(
            "RELATE $from->edge->$to SET user_id = $uid, strength = $str, "
            "created_at = $cat, last_traversed_at = time::now()",
            {
                "from": _rid(e["in"]),
                "to": new_rid,
                "uid": e["user_id"],
                "str": e["strength"],
                "cat": e["created_at"],
            },
        )
    outgoing = await db.query("SELECT * FROM edge WHERE in = $old", {"old": old_rid})
    for e in _rows(outgoing):
        await db.query(
            "RELATE $from->edge->$to SET user_id = $uid, strength = $str, "
            "created_at = $cat, last_traversed_at = time::now()",
            {
                "from": new_rid,
                "to": _rid(e["out"]),
                "uid": e["user_id"],
                "str": e["strength"],
                "cat": e["created_at"],
            },
        )
    await db.query("DELETE edge WHERE in = $old OR out = $old", {"old": old_rid})


# --- Stats ---


async def get_graph_stats(user_id: str) -> dict:
    db = await get_client()
    node_count = await db.query(
        "SELECT count() AS c FROM node WHERE user_id = $uid GROUP ALL",
        {"uid": user_id},
    )
    edge_count = await db.query(
        "SELECT count() AS c FROM edge WHERE user_id = $uid GROUP ALL",
        {"uid": user_id},
    )
    stream_count = await db.query(
        "SELECT count() AS c FROM raw_stream WHERE user_id = $uid GROUP ALL",
        {"uid": user_id},
    )
    return {
        "nodes": _count(node_count),
        "edges": _count(edge_count),
        "stream_entries": _count(stream_count),
    }


# --- Reset ---


async def reset_graph(user_id: str) -> None:
    db = await get_client()
    await db.query("DELETE edge WHERE user_id = $uid", {"uid": user_id})
    await db.query("DELETE node WHERE user_id = $uid", {"uid": user_id})
    await db.query("DELETE raw_stream WHERE user_id = $uid", {"uid": user_id})
    logger.info("graph_reset", user_id=user_id)
