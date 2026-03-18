import uuid
from datetime import datetime
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from src.config import get_settings
from src.telemetry.logger import get_logger

_log = get_logger("db.supabase")
_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            init=_init_connection,
            statement_cache_size=0,
        )
        _log.info("db.pool_created")
    except Exception as e:
        _log.error("db.pool_failed", error=str(e))
        if settings.ENVIRONMENT != "development":
            raise
        _log.warning("db.running_without_pool")


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        _log.info("db.pool_closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized — call init_pool() first")
    return _pool


# Keep the old name as an alias for internal usage
_get_pool = get_pool


async def save_message(
    user_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import json

    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO messages (user_id, role, content, metadata)
        VALUES ($1, $2, $3, $4)
        RETURNING id, user_id, role, content, created_at, metadata
        """,
        user_id,
        role,
        content,
        json.dumps(metadata or {}),
    )
    return dict(row)


async def get_messages(
    user_id: str,
    limit: int = 50,
    before_id: str | None = None,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    if before_id:
        rows = await pool.fetch(
            """
            SELECT id, user_id, role, content, created_at, metadata
            FROM messages
            WHERE user_id = $1 AND created_at < (
                SELECT created_at FROM messages WHERE id = $2::uuid
            )
            ORDER BY created_at DESC
            LIMIT $3
            """,
            user_id,
            before_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, user_id, role, content, created_at, metadata
            FROM messages
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [dict(r) for r in rows]


async def get_messages_by_ids(
    user_id: str,
    message_ids: list[str],
) -> list[dict[str, Any]]:
    if not message_ids:
        return []
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT id, user_id, role, content, created_at, metadata
        FROM messages
        WHERE user_id = $1 AND id = ANY($2::uuid[])
        ORDER BY created_at ASC
        """,
        user_id,
        message_ids,
    )
    return [dict(r) for r in rows]


async def save_item(
    user_id: str,
    raw_text: str,
    interpreted_action: str,
    deadline_type: str | None = None,
    deadline_at: str | datetime | None = None,
    urgency_score: float = 0.0,
    energy_estimate: str | None = None,
    source_message_id: str | None = None,
    entity_ids: list[str] | None = None,
) -> dict[str, Any]:
    pool = _get_pool()

    # asyncpg requires datetime objects for TIMESTAMPTZ, not strings.
    # LLM extraction returns deadline_at as an ISO string.
    parsed_deadline = None
    if deadline_at is not None:
        if isinstance(deadline_at, str):
            parsed_deadline = datetime.fromisoformat(deadline_at)
        else:
            parsed_deadline = deadline_at

    row = await pool.fetchrow(
        """
        INSERT INTO items (
            user_id, raw_text, interpreted_action, deadline_type,
            deadline_at, urgency_score, energy_estimate,
            source_message_id, entity_ids
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid, $9::uuid[])
        RETURNING *
        """,
        user_id,
        raw_text,
        interpreted_action,
        deadline_type,
        parsed_deadline,
        urgency_score,
        energy_estimate,
        source_message_id,
        entity_ids or [],
    )
    return dict(row)


async def get_open_items(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM items
        WHERE user_id = $1 AND status = 'open'
        ORDER BY urgency_score DESC, created_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def get_urgent_items(user_id: str, hours: int = 48) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM items
        WHERE user_id = $1
          AND status = 'open'
          AND deadline_at IS NOT NULL
          AND deadline_at < now() + ($2 || ' hours')::interval
        ORDER BY deadline_at ASC
        """,
        user_id,
        str(hours),
    )
    return [dict(r) for r in rows]


_ITEM_ALLOWED_COLUMNS = frozenset(
    {
        "raw_text",
        "interpreted_action",
        "deadline_type",
        "deadline_at",
        "urgency_score",
        "energy_estimate",
        "status",
        "last_surfaced_at",
        "nudge_after",
        "embedding",
        "recurrence_id",
        "entity_ids",
        "source_message_id",
    }
)

_PROFILE_ALLOWED_COLUMNS = frozenset(
    {
        "display_name",
        "timezone",
        "tone_preference",
        "length_preference",
        "pushiness_preference",
        "uses_emoji",
        "primary_language",
        "google_calendar_connected",
        "notification_sent_today",
        "last_interaction_at",
        "patterns",
    }
)

_SUBSCRIPTION_ALLOWED_COLUMNS = frozenset(
    {
        "tier",
        "stripe_customer_id",
        "stripe_subscription_id",
        "status",
        "current_period_end",
    }
)


def _validate_columns(
    fields: dict[str, Any], allowed: frozenset[str], context: str
) -> None:
    invalid = set(fields.keys()) - allowed
    if invalid:
        raise ValueError(f"Disallowed columns in {context}: {invalid}")


async def update_item(item_id: str, user_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        raise ValueError("No fields to update")

    _validate_columns(fields, _ITEM_ALLOWED_COLUMNS, "update_item")

    pool = _get_pool()
    set_clauses = []
    params: list[Any] = []
    for i, (key, value) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        params.append(value)

    params.append(item_id)
    params.append(user_id)
    query = f"""
        UPDATE items SET {", ".join(set_clauses)}
        WHERE id = ${len(params) - 1}::uuid AND user_id = ${len(params)}
        RETURNING *
    """
    row = await pool.fetchrow(query, *params)
    if not row:
        raise ValueError(f"Item {item_id} not found")
    return dict(row)


async def search_items_semantic(
    user_id: str,
    embedding: list[float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT *, embedding <=> $2::vector AS distance
        FROM items
        WHERE user_id = $1 AND embedding IS NOT NULL
        ORDER BY embedding <=> $2::vector
        LIMIT $3
        """,
        user_id,
        embedding,
        limit,
    )
    return [dict(r) for r in rows]


async def search_items_hybrid(
    user_id: str,
    embedding: list[float],
    query_text: str,
    limit: int = 5,
    vector_weight: float = 0.7,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    text_weight = 1.0 - vector_weight
    rows = await pool.fetch(
        """
        SELECT *,
            ($5 * COALESCE(1.0 - (embedding <=> $2::vector), 0)) +
            ($6 * COALESCE(ts_rank(search_text, plainto_tsquery('english', $3)), 0))
            AS hybrid_score
        FROM items
        WHERE user_id = $1
          AND status = 'open'
          AND (embedding IS NOT NULL OR search_text @@ plainto_tsquery('english', $3))
        ORDER BY hybrid_score DESC
        LIMIT $4
        """,
        user_id,
        embedding,
        query_text,
        limit,
        vector_weight,
        text_weight,
    )
    return [dict(r) for r in rows]


async def search_items_text(
    user_id: str,
    query_text: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT *, ts_rank(search_text, plainto_tsquery('english', $2)) AS rank
        FROM items
        WHERE user_id = $1
          AND search_text @@ plainto_tsquery('english', $2)
        ORDER BY rank DESC
        LIMIT $3
        """,
        user_id,
        query_text,
        limit,
    )
    return [dict(r) for r in rows]


async def get_profile(user_id: str) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM user_profiles WHERE id = $1::uuid",
        user_id,
    )
    if not row:
        return {}
    return dict(row)


async def update_profile(user_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        raise ValueError("No fields to update")

    _validate_columns(fields, _PROFILE_ALLOWED_COLUMNS, "update_profile")

    pool = _get_pool()
    set_clauses = []
    params: list[Any] = []
    for i, (key, value) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        params.append(value)

    params.append(user_id)
    query = f"""
        UPDATE user_profiles SET {", ".join(set_clauses)}
        WHERE id = ${len(params)}::uuid
        RETURNING *
    """
    row = await pool.fetchrow(query, *params)
    if not row:
        raise ValueError(f"Profile for user {user_id} not found")
    return dict(row)


async def save_memory(
    user_id: str,
    type: str,
    content: str,
    source_message_id: str | None = None,
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO memories (user_id, type, content, source_message_id, embedding)
        VALUES ($1, $2, $3, $4::uuid, $5::vector)
        RETURNING *
        """,
        user_id,
        type,
        content,
        source_message_id,
        embedding,
    )
    return dict(row)


async def search_memories_semantic(
    user_id: str,
    embedding: list[float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT *, embedding <=> $2::vector AS distance
        FROM memories
        WHERE user_id = $1 AND embedding IS NOT NULL
        ORDER BY embedding <=> $2::vector
        LIMIT $3
        """,
        user_id,
        embedding,
        limit,
    )
    return [dict(r) for r in rows]


async def save_llm_usage(
    trace_id: str,
    user_id: str,
    step_id: str,
    pipeline: str,
    variant: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    ttft_ms: int | None = None,
    config_hash: str | None = None,
) -> None:
    pool = _get_pool()
    await pool.execute(
        """
        INSERT INTO llm_usage (
            trace_id, user_id, step_id, pipeline, variant,
            model, provider, input_tokens, output_tokens, latency_ms,
            ttft_ms, config_hash
        )
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        trace_id,
        user_id,
        step_id,
        pipeline,
        variant,
        model,
        provider,
        input_tokens,
        output_tokens,
        latency_ms,
        ttft_ms,
        config_hash,
    )


async def save_item_event(
    item_id: str,
    user_id: str,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import json

    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO item_events (item_id, user_id, event_type, metadata)
        VALUES ($1::uuid, $2, $3, $4)
        RETURNING *
        """,
        item_id,
        user_id,
        event_type,
        json.dumps(metadata or {}),
    )
    return dict(row)


async def get_proactive_items(user_id: str, hours: int = 24) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM items
        WHERE user_id = $1
          AND status = 'open'
          AND deadline_type = 'hard'
          AND deadline_at IS NOT NULL
          AND deadline_at < now() + ($2 || ' hours')::interval
        ORDER BY deadline_at ASC
        """,
        user_id,
        str(hours),
    )
    return [dict(r) for r in rows]


async def get_slipped_items(user_id: str) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM items
        WHERE user_id = $1
          AND status = 'open'
          AND deadline_type = 'soft'
          AND deadline_at IS NOT NULL
          AND deadline_at < now()
        ORDER BY deadline_at ASC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def get_last_interaction(user_id: str) -> str | None:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT last_interaction_at FROM user_profiles WHERE id = $1::uuid",
        user_id,
    )
    if row and row["last_interaction_at"]:
        return str(row["last_interaction_at"])
    return None


async def save_oauth_token(
    user_id: str,
    provider: str,
    refresh_token: str,
    scopes: list[str],
) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO oauth_tokens (user_id, provider, refresh_token, scopes)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, provider) DO UPDATE
        SET refresh_token = EXCLUDED.refresh_token,
            scopes = EXCLUDED.scopes,
            updated_at = now()
        RETURNING *
        """,
        user_id,
        provider,
        refresh_token,
        scopes,
    )
    return dict(row)


async def get_recently_done_count(user_id: str, hours: int = 24) -> int:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        SELECT COUNT(*) as cnt FROM item_events
        WHERE user_id = $1
          AND event_type = 'done'
          AND created_at > now() - ($2 || ' hours')::interval
        """,
        user_id,
        str(hours),
    )
    return int(row["cnt"]) if row else 0


async def get_user_tier(user_id: str) -> str:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT tier FROM subscriptions WHERE user_id = $1",
        user_id,
    )
    if row and row.get("tier"):
        return str(row["tier"])
    return "free"


async def get_users_with_urgent_deadlines(hours: int = 24) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT i.user_id, i.interpreted_action, i.deadline_at,
               p.timezone, p.notification_sent_today
        FROM items i
        JOIN user_profiles p ON p.id = i.user_id
        WHERE i.deadline_type = 'hard'
          AND i.status = 'open'
          AND i.deadline_at IS NOT NULL
          AND i.deadline_at < now() + ($1 || ' hours')::interval
          AND i.deadline_at > now()
        ORDER BY i.deadline_at ASC
        """,
        str(hours),
    )
    return [dict(r) for r in rows]


async def get_push_subscriptions(user_id: str) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        "SELECT * FROM push_subscriptions WHERE user_id = $1",
        user_id,
    )
    return [dict(r) for r in rows]


async def delete_push_subscription(user_id: str, endpoint: str) -> None:
    pool = _get_pool()
    await pool.execute(
        "DELETE FROM push_subscriptions WHERE user_id = $1 AND endpoint = $2",
        user_id,
        endpoint,
    )


async def save_push_subscription(
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth_key: str,
) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth_key)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, endpoint) DO UPDATE
        SET p256dh = EXCLUDED.p256dh, auth_key = EXCLUDED.auth_key
        RETURNING *
        """,
        user_id,
        endpoint,
        p256dh,
        auth_key,
    )
    return dict(row)


async def get_all_open_items_for_decay() -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT id, user_id, urgency_score, deadline_type, deadline_at, created_at
        FROM items
        WHERE status = 'open'
        """,
    )
    return [dict(r) for r in rows]


async def batch_update_items(updates: list[dict[str, Any]]) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for original in updates:
                upd = dict(original)  # copy to avoid mutating caller's dicts
                item_id = upd.pop("id")
                user_id = upd.pop("user_id")
                if not upd:
                    continue
                _validate_columns(upd, _ITEM_ALLOWED_COLUMNS, "batch_update_items")
                set_clauses = []
                params: list[Any] = []
                for i, (key, value) in enumerate(upd.items(), start=1):
                    set_clauses.append(f"{key} = ${i}")
                    params.append(value)
                params.append(item_id)
                params.append(user_id)
                query = f"""
                    UPDATE items SET {", ".join(set_clauses)}
                    WHERE id = ${len(params) - 1}::uuid AND user_id = ${len(params)}
                """
                await conn.execute(query, *params)


async def get_items_without_embeddings(user_id: str) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM items
        WHERE user_id = $1 AND embedding IS NULL AND status = 'open'
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def update_item_embedding(
    item_id: str, user_id: str, embedding: list[float]
) -> None:
    pool = _get_pool()
    await pool.execute(
        "UPDATE items SET embedding = $3::vector WHERE id = $1::uuid AND user_id = $2",
        item_id,
        user_id,
        embedding,
    )


async def save_entity(
    user_id: str,
    name: str,
    entity_type: str,
    context: str,
) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO entities (user_id, name, type, context)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, name, type) DO UPDATE
        SET context = EXCLUDED.context, updated_at = now()
        RETURNING *
        """,
        user_id,
        name,
        entity_type,
        context,
    )
    return dict(row)


async def get_calendar_connected_users() -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        "SELECT * FROM user_profiles WHERE google_calendar_connected = true",
    )
    return [dict(r) for r in rows]


async def get_oauth_token(user_id: str) -> dict[str, Any] | None:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM oauth_tokens WHERE user_id = $1 AND provider = 'google'",
        user_id,
    )
    return dict(row) if row else None


async def upsert_calendar_events(
    user_id: str,
    events: list[dict[str, Any]],
) -> None:
    if not events:
        return
    pool = _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for event in events:
                await conn.execute(
                    """
                    INSERT INTO calendar_events (
                        user_id, google_event_id, summary,
                        start_at, end_at, location, description, is_all_day
                    )
                    VALUES ($1, $2, $3, $4::timestamptz, $5::timestamptz, $6, $7, $8)
                    ON CONFLICT (user_id, google_event_id) DO UPDATE
                    SET summary = EXCLUDED.summary,
                        start_at = EXCLUDED.start_at,
                        end_at = EXCLUDED.end_at,
                        location = EXCLUDED.location,
                        description = EXCLUDED.description,
                        is_all_day = EXCLUDED.is_all_day,
                        updated_at = now()
                    """,
                    user_id,
                    event["google_event_id"],
                    event["summary"],
                    event["start_at"],
                    event["end_at"],
                    event.get("location"),
                    event.get("description"),
                    event.get("is_all_day", False),
                )


async def disconnect_calendar(user_id: str) -> None:
    pool = _get_pool()
    await pool.execute(
        "UPDATE user_profiles SET google_calendar_connected = false WHERE id = $1::uuid",
        user_id,
    )


async def get_active_users(days: int = 30) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM user_profiles
        WHERE last_interaction_at > now() - ($1 || ' days')::interval
        """,
        str(days),
    )
    return [dict(r) for r in rows]


async def get_completion_stats(user_id: str) -> dict[str, Any]:
    pool = _get_pool()

    dow_rows = await pool.fetch(
        """
        SELECT EXTRACT(DOW FROM created_at)::int AS dow, COUNT(*) AS cnt
        FROM item_events
        WHERE user_id = $1 AND event_type = 'done'
          AND created_at > now() - interval '30 days'
        GROUP BY dow
        ORDER BY dow
        """,
        user_id,
    )
    completions_by_dow = {str(r["dow"]): int(r["cnt"]) for r in dow_rows}

    total_row = await pool.fetchrow(
        """
        SELECT COUNT(*) AS total FROM item_events
        WHERE user_id = $1 AND event_type = 'done'
          AND created_at > now() - interval '30 days'
        """,
        user_id,
    )
    total = int(total_row["total"]) if total_row else 0

    return {
        "completions_by_dow": completions_by_dow,
        "total_completed": total,
        "avg_daily": round(total / 30, 2) if total else 0.0,
    }


async def get_message_activity(user_id: str, days: int = 30) -> list[dict[str, Any]]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT created_at::date AS day,
               COUNT(*) FILTER (WHERE role = 'user') AS user_msgs,
               COUNT(*) FILTER (WHERE role = 'assistant') AS assistant_msgs
        FROM messages
        WHERE user_id = $1
          AND created_at > now() - ($2 || ' days')::interval
        GROUP BY day
        ORDER BY day
        """,
        user_id,
        str(days),
    )
    return [dict(r) for r in rows]


async def get_user_messages_text(
    user_id: str,
    days: int = 30,
    limit: int = 50,
) -> list[str]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT content FROM messages
        WHERE user_id = $1 AND role = 'user'
          AND created_at > now() - ($2 || ' days')::interval
        ORDER BY created_at DESC
        LIMIT $3
        """,
        user_id,
        str(days),
        limit,
    )
    return [r["content"] for r in rows]


async def get_user_first_interaction(user_id: str) -> str | None:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT MIN(created_at) AS first_at FROM messages WHERE user_id = $1",
        user_id,
    )
    if row and row["first_at"]:
        return row["first_at"].isoformat()
    return None


# --- Filtered query functions (used by smart_fetch tool) ---


async def get_items_filtered(
    user_id: str,
    entity_id: str | None = None,
    since: datetime | None = None,
    status: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    conditions = ["user_id = $1"]
    params: list[Any] = [user_id]
    idx = 2

    if status and status != "all":
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if since:
        conditions.append(f"created_at >= ${idx}")
        params.append(since)
        idx += 1
    if entity_id:
        conditions.append(f"${idx} = ANY(entity_ids)")
        params.append(entity_id)
        idx += 1

    where = " AND ".join(conditions)
    params.append(limit)
    query = f"""
        SELECT * FROM items
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def get_memories_filtered(
    user_id: str,
    since: datetime | None = None,
    search_text: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    conditions = ["user_id = $1"]
    params: list[Any] = [user_id]
    idx = 2

    if since:
        conditions.append(f"created_at >= ${idx}")
        params.append(since)
        idx += 1
    if search_text:
        conditions.append(f"search_text @@ plainto_tsquery('english', ${idx})")
        params.append(search_text)
        idx += 1

    where = " AND ".join(conditions)
    params.append(limit)
    query = f"""
        SELECT * FROM memories
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def get_messages_filtered(
    user_id: str,
    since: datetime | None = None,
    search_text: str | None = None,
    role: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    conditions = ["user_id = $1"]
    params: list[Any] = [user_id]
    idx = 2

    if since:
        conditions.append(f"created_at >= ${idx}")
        params.append(since)
        idx += 1
    if search_text:
        conditions.append(f"content ILIKE ${idx} ESCAPE '\\'")
        escaped = (
            search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        params.append(f"%{escaped}%")
        idx += 1
    if role:
        conditions.append(f"role = ${idx}")
        params.append(role)
        idx += 1

    where = " AND ".join(conditions)
    params.append(limit)
    query = f"""
        SELECT id, role, content, created_at FROM messages
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def get_calendar_events_filtered(
    user_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    pool = _get_pool()
    conditions = ["user_id = $1"]
    params: list[Any] = [user_id]
    idx = 2

    if since:
        conditions.append(f"start_at >= ${idx}")
        params.append(since)
        idx += 1
    if until:
        conditions.append(f"start_at <= ${idx}")
        params.append(until)
        idx += 1

    where = " AND ".join(conditions)
    params.append(limit)
    query = f"""
        SELECT * FROM calendar_events
        WHERE {where}
        ORDER BY start_at ASC
        LIMIT ${idx}
    """
    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def resolve_entity(user_id: str, name: str) -> str | None:
    pool = _get_pool()
    # Use case-insensitive exact match, not ILIKE, to prevent wildcard injection
    row = await pool.fetchrow(
        """
        SELECT id FROM entities
        WHERE user_id = $1 AND (LOWER(name) = LOWER($2) OR LOWER($2) = ANY(
            SELECT LOWER(a) FROM unnest(aliases) AS a
        ))
        LIMIT 1
        """,
        user_id,
        name,
    )
    if row:
        return str(row["id"])
    return None


async def create_subscription(
    user_id: str,
    tier: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    current_period_end: str | None = None,
) -> dict[str, Any]:
    pool = _get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO subscriptions (
            user_id, tier, stripe_customer_id, stripe_subscription_id,
            current_period_end, status
        )
        VALUES ($1, $2, $3, $4, $5::timestamptz, 'active')
        ON CONFLICT (user_id) DO UPDATE
        SET tier = EXCLUDED.tier,
            stripe_customer_id = EXCLUDED.stripe_customer_id,
            stripe_subscription_id = EXCLUDED.stripe_subscription_id,
            current_period_end = EXCLUDED.current_period_end,
            status = 'active',
            updated_at = now()
        RETURNING *
        """,
        user_id,
        tier,
        stripe_customer_id,
        stripe_subscription_id,
        current_period_end,
    )
    return dict(row)


async def update_subscription(user_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        raise ValueError("No fields to update")

    _validate_columns(fields, _SUBSCRIPTION_ALLOWED_COLUMNS, "update_subscription")

    pool = _get_pool()
    set_clauses = []
    params: list[Any] = []
    for i, (key, value) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        params.append(value)

    params.append(user_id)
    query = f"""
        UPDATE subscriptions SET {", ".join(set_clauses)}, updated_at = now()
        WHERE user_id = ${len(params)}
        RETURNING *
    """
    row = await pool.fetchrow(query, *params)
    if not row:
        raise ValueError(f"Subscription for user {user_id} not found")
    return dict(row)


async def get_subscription(user_id: str) -> dict[str, Any] | None:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM subscriptions WHERE user_id = $1",
        user_id,
    )
    return dict(row) if row else None


async def delete_user_data(user_id: str) -> dict[str, int]:
    """Delete all user data across all tables. Returns count of deleted rows per table."""
    pool = _get_pool()
    uid = uuid.UUID(user_id)
    counts: dict[str, int] = {}

    # Order matters: delete from child tables first to respect FK constraints.
    # Most tables use `user_id`, but `user_profiles` uses `id` as the PK.
    tables_with_user_id = [
        "item_events",
        "items",
        "memories",
        "entities",
        "recurrences",
        "calendar_events",
        "messages",
        "push_subscriptions",
        "experiment_assignments",
        "oauth_tokens",
        "subscriptions",
        "llm_usage",
        "memory_edges",
        "memory_nodes",
    ]

    async with pool.acquire() as conn:
        async with conn.transaction():
            for table in tables_with_user_id:
                result = await conn.execute(
                    f"DELETE FROM {table} WHERE user_id = $1",
                    uid,
                )
                count = int(result.split()[-1]) if result else 0
                counts[table] = count

            # user_profiles uses `id` as PK, not `user_id`
            result = await conn.execute(
                "DELETE FROM user_profiles WHERE id = $1",
                uid,
            )
            counts["user_profiles"] = int(result.split()[-1]) if result else 0

    _log.info("user.data_deleted", user_id=user_id, counts=counts)
    return counts


async def get_subscription_by_customer(customer_id: str) -> dict[str, Any] | None:
    pool = _get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM subscriptions WHERE stripe_customer_id = $1",
        customer_id,
    )
    return dict(row) if row else None
