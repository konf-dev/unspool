"""Admin endpoints — admin-key-authed."""

import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from src.api.health_checks import run_all_checks
from src.auth.admin_auth import verify_admin_key
from src.core.database import AsyncSessionLocal
from src.core.settings import get_settings
from src.telemetry.logger import get_logger
from src.telemetry.middleware import GIT_SHA

_log = get_logger("api.admin")

router = APIRouter(dependencies=[Depends(verify_admin_key)])


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        # Messages for this trace
        messages = await session.execute(text("""
            SELECT id, user_id, event_type, payload, created_at
            FROM event_stream
            WHERE payload->'metadata'->>'trace_id' = :trace_id
            ORDER BY created_at
        """), {"trace_id": trace_id})

        # LLM usage for this trace
        usage = await session.execute(text("""
            SELECT id, pipeline, model, input_tokens, output_tokens,
                   latency_ms, created_at
            FROM llm_usage
            WHERE trace_id = :trace_id
            ORDER BY created_at
        """), {"trace_id": trace_id})

    return {
        "trace_id": trace_id,
        "events": [dict(r) for r in messages.mappings().all()],
        "llm_usage": [dict(r) for r in usage.mappings().all()],
    }


@router.get("/user/{user_id}/messages")
async def get_user_messages(
    user_id: str,
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(text("""
            SELECT id, role, content, metadata, created_at
            FROM vw_messages
            WHERE user_id = :uid            ORDER BY created_at DESC
            LIMIT :limit
        """), {"uid": user_id, "limit": limit})
    return [dict(r) for r in rows.mappings().all()]


@router.get("/user/{user_id}/graph")
async def get_user_graph(
    user_id: str,
    limit: int = Query(default=100, le=500),
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        nodes = await session.execute(text("""
            SELECT id, content, node_type, created_at, updated_at
            FROM graph_nodes
            WHERE user_id = :uid            ORDER BY updated_at DESC
            LIMIT :limit
        """), {"uid": user_id, "limit": limit})

        edges = await session.execute(text("""
            SELECT id, source_node_id, target_node_id, edge_type, weight, metadata, created_at
            FROM graph_edges
            WHERE user_id = :uid            ORDER BY created_at DESC
            LIMIT :limit
        """), {"uid": user_id, "limit": limit})

    return {
        "nodes": [dict(r) for r in nodes.mappings().all()],
        "edges": [dict(r) for r in edges.mappings().all()],
    }


@router.get("/user/{user_id}/profile")
async def get_user_profile(user_id: str) -> dict[str, Any]:
    from src.db.queries import get_profile
    profile = await get_profile(user_id)
    if not profile:
        return {"error": "Profile not found"}
    return profile


@router.patch("/user/{user_id}/profile")
async def patch_user_profile(user_id: str, body: dict[str, Any]) -> dict[str, str]:
    import uuid as _uuid
    from datetime import datetime as _dt
    from fastapi import HTTPException as _HTTPException
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.core.models import UserProfile
    from src.db.queries import update_profile
    allowed = {"last_interaction_at", "last_proactive_at", "timezone", "display_name",
               "tone_preference", "length_preference", "pushiness_preference", "feed_token"}
    datetime_fields = {"last_interaction_at", "last_proactive_at"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        raise _HTTPException(status_code=422, detail="No valid fields provided")
    # Parse datetime strings into datetime objects
    for key in datetime_fields:
        if key in fields and isinstance(fields[key], str):
            fields[key] = _dt.fromisoformat(fields[key])
    # Ensure profile exists (upsert) before updating
    async with AsyncSessionLocal() as session:
        stmt = pg_insert(UserProfile).values(id=_uuid.UUID(user_id)).on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()
    await update_profile(user_id, **fields)
    return {"status": "updated"}


@router.get("/jobs/recent")
async def get_recent_jobs(
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(text("""
            SELECT id, trace_id, user_id, pipeline, model,
                   input_tokens, output_tokens, latency_ms, created_at
            FROM llm_usage
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]


@router.get("/errors")
async def get_recent_errors(
    limit: int = Query(default=20, le=100),
    source: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        if source:
            rows = await session.execute(text("""
                SELECT id, trace_id, user_id, source, error_type, error_message,
                       stacktrace, metadata, created_at
                FROM error_log
                WHERE source = :source
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"source": source, "limit": limit})
        else:
            rows = await session.execute(text("""
                SELECT id, trace_id, user_id, source, error_type, error_message,
                       stacktrace, metadata, created_at
                FROM error_log
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": limit})
    return [dict(r) for r in rows.mappings().all()]


@router.get("/errors/summary")
async def get_error_summary() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(text("""
            SELECT source, error_type, COUNT(*) as count,
                   MAX(created_at) as last_seen
            FROM error_log
            WHERE created_at > NOW() - interval '24 hours'
            GROUP BY source, error_type
            ORDER BY count DESC
        """))
    return [dict(r) for r in rows.mappings().all()]


@router.delete("/eval-cleanup")
async def eval_cleanup() -> dict[str, Any]:
    from src.auth.supabase_auth import EVAL_USER_ID
    from src.db.queries import delete_user_data

    counts = await delete_user_data(EVAL_USER_ID)
    _log.info("eval.cleanup", user_id=EVAL_USER_ID, counts=counts)
    return {"user_id": EVAL_USER_ID, "deleted": counts}


@router.get("/health/deep")
async def health_deep() -> dict[str, Any]:
    settings = get_settings()
    start = time.perf_counter()

    services = await run_all_checks()
    total_ms = round((time.perf_counter() - start) * 1000)

    any_error = any(s["status"] == "error" for s in services.values())
    status = "degraded" if any_error else "ok"

    return {
        "status": status,
        "git_sha": GIT_SHA,
        "environment": settings.ENVIRONMENT,
        "total_ms": total_ms,
        "services": services,
    }
