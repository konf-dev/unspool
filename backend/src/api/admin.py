from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth.admin_auth import verify_admin_key
from src.db.supabase import get_pool
from src.telemetry.logger import get_logger

_log = get_logger("api.admin")

router = APIRouter(dependencies=[Depends(verify_admin_key)])


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    pool = get_pool()

    # Get messages for this trace
    messages = await pool.fetch(
        """
        SELECT id, role, content, created_at, metadata
        FROM messages
        WHERE metadata->>'trace_id' = $1
        ORDER BY created_at
        """,
        trace_id,
    )

    # Get LLM usage for this trace
    usage = await pool.fetch(
        """
        SELECT step_id, pipeline, variant, model, provider,
               input_tokens, output_tokens, latency_ms, ttft_ms,
               config_hash, created_at
        FROM llm_usage
        WHERE trace_id = $1::uuid
        ORDER BY created_at
        """,
        trace_id,
    )

    return {
        "trace_id": trace_id,
        "messages": [dict(r) for r in messages],
        "llm_usage": [dict(r) for r in usage],
    }


@router.get("/user/{user_id}/messages")
async def get_user_messages(
    user_id: str,
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, role, content, created_at, metadata
        FROM messages
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


@router.get("/user/{user_id}/items")
async def get_user_items(
    user_id: str,
    status: str = Query(default="open"),
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, raw_text, interpreted_action, deadline_type, deadline_at,
               urgency_score, energy_estimate, status, created_at,
               last_surfaced_at, nudge_after
        FROM items
        WHERE user_id = $1 AND status = $2
        ORDER BY created_at DESC
        """,
        user_id,
        status,
    )
    return [dict(r) for r in rows]


@router.get("/user/{user_id}/profile")
async def get_user_profile(user_id: str) -> dict[str, Any]:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, display_name, timezone, tone_preference, length_preference,
               pushiness_preference, uses_emoji, primary_language,
               google_calendar_connected, notification_sent_today,
               last_interaction_at, patterns, created_at
        FROM user_profiles
        WHERE id = $1
        """,
        user_id,
    )
    if not row:
        return {"error": "Profile not found"}
    return dict(row)


@router.get("/jobs/recent")
async def get_recent_jobs(
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT trace_id, user_id, step_id, pipeline, variant, model,
               input_tokens, output_tokens, latency_ms, created_at
        FROM llm_usage
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


@router.delete("/eval-cleanup")
async def eval_cleanup() -> dict[str, Any]:
    """Delete all data for the eval user. Called before each eval run."""
    from src.auth.supabase_auth import EVAL_USER_ID

    pool = get_pool()
    deleted_messages = await pool.fetchval(
        "DELETE FROM messages WHERE user_id = $1 RETURNING count(*)",
        EVAL_USER_ID,
    )
    deleted_items = await pool.fetchval(
        "DELETE FROM items WHERE user_id = $1 RETURNING count(*)",
        EVAL_USER_ID,
    )
    deleted_usage = await pool.fetchval(
        "DELETE FROM llm_usage WHERE user_id = $1 RETURNING count(*)",
        EVAL_USER_ID,
    )
    _log.info(
        "eval.cleanup",
        user_id=EVAL_USER_ID,
        deleted_messages=deleted_messages or 0,
        deleted_items=deleted_items or 0,
        deleted_usage=deleted_usage or 0,
    )
    return {
        "user_id": EVAL_USER_ID,
        "deleted_messages": deleted_messages or 0,
        "deleted_items": deleted_items or 0,
        "deleted_usage": deleted_usage or 0,
    }


@router.get("/errors")
async def get_recent_errors(
    limit: int = Query(default=20, le=100),
    source: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    pool = get_pool()
    if source:
        rows = await pool.fetch(
            """
            SELECT id, trace_id, user_id, source, error_type, error_message,
                   stacktrace, metadata, created_at
            FROM error_log
            WHERE source = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            source,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, trace_id, user_id, source, error_type, error_message,
                   stacktrace, metadata, created_at
            FROM error_log
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/errors/summary")
async def get_error_summary() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT source, error_type, COUNT(*) as count,
               MAX(created_at) as last_seen
        FROM error_log
        WHERE created_at > now() - interval '24 hours'
        GROUP BY source, error_type
        ORDER BY count DESC
        """
    )
    return [dict(r) for r in rows]
