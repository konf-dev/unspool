"""All non-graph DB operations — profiles, subscriptions, messages, errors, etc."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.models import (
    EventStream,
    UserProfile,
    Subscription,
    PushSubscription,
    ProactiveMessage,
    ScheduledAction,
    ErrorLog,
    LLMUsage,
    GraphNode,
    GraphEdge,
)


# ──────────────────────────── Messages (via event_stream) ────────────

async def get_messages_from_events(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    before: str | None = None,
) -> list[dict[str, Any]]:
    """Query vw_messages view for paginated chat history."""
    if before:
        query = text(
            "SELECT id, user_id, role, content, metadata, created_at "
            "FROM vw_messages "
            "WHERE user_id = CAST(:user_id AS uuid) "
            "  AND (created_at, id) < ("
            "    SELECT created_at, id FROM event_stream WHERE id = CAST(:before_id AS uuid)"
            "  ) "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT :lim"
        )
        params: dict[str, Any] = {"user_id": user_id, "before_id": before, "lim": limit}
    else:
        query = text(
            "SELECT id, user_id, role, content, metadata, created_at "
            "FROM vw_messages "
            "WHERE user_id = CAST(:user_id AS uuid) "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT :lim"
        )
        params = {"user_id": user_id, "lim": limit}

    result = await session.execute(query, params)
    return [dict(r) for r in result.mappings().all()]


async def append_message_event(
    session: AsyncSession,
    user_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> EventStream:
    """Append a MessageReceived or AgentReplied event."""
    event_type = "MessageReceived" if role == "user" else "AgentReplied"
    event = EventStream(
        user_id=uuid.UUID(user_id),
        event_type=event_type,
        payload={"content": content, "metadata": metadata or {}},
    )
    session.add(event)
    await session.flush()
    return event


# ──────────────────────────── Profiles ───────────────────────────────

async def get_profile(user_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        stmt = select(UserProfile).where(UserProfile.id == uuid.UUID(user_id))
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        return {
            "id": str(profile.id),
            "display_name": profile.display_name,
            "timezone": profile.timezone,
            "tone_preference": profile.tone_preference,
            "length_preference": profile.length_preference,
            "pushiness_preference": profile.pushiness_preference,
            "uses_emoji": profile.uses_emoji,
            "primary_language": profile.primary_language,
            "patterns": profile.patterns,
            "last_interaction_at": profile.last_interaction_at.isoformat() if profile.last_interaction_at else None,
            "last_proactive_at": profile.last_proactive_at.isoformat() if profile.last_proactive_at else None,
            "notification_sent_today": profile.notification_sent_today,
            "feed_token": profile.feed_token,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        }


async def update_profile(user_id: str, **fields: Any) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(UserProfile).where(
                UserProfile.id == uuid.UUID(user_id)
            ).values(**fields)
        )
        if result.rowcount == 0:
            # Profile doesn't exist yet — create it with the given fields
            profile = UserProfile(id=uuid.UUID(user_id), **fields)
            session.add(profile)
        await session.commit()


async def get_active_users(days: int = 30) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(UserProfile).where(
            UserProfile.last_interaction_at >= cutoff
        )
        result = await session.execute(stmt)
        return [{"id": str(p.id)} for p in result.scalars().all()]


# ──────────────────────────── Subscriptions ──────────────────────────

async def get_user_tier(user_id: str) -> str:
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription.tier).where(
            Subscription.user_id == uuid.UUID(user_id),
            Subscription.status == "active",
        )
        result = await session.execute(stmt)
        tier = result.scalar_one_or_none()
        return tier or "free"


async def create_subscription(
    user_id: str,
    tier: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO subscriptions (user_id, tier, stripe_customer_id, stripe_subscription_id, status)
                VALUES (CAST(:uid AS uuid), :tier, :cid, :sid, 'active')
                ON CONFLICT (user_id) DO UPDATE SET
                    tier = EXCLUDED.tier,
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    status = 'active'
            """),
            {"uid": user_id, "tier": tier, "cid": stripe_customer_id, "sid": stripe_subscription_id},
        )
        await session.commit()


async def update_subscription(user_id: str, **fields: Any) -> None:
    async with AsyncSessionLocal() as session:
        stmt = update(Subscription).where(
            Subscription.user_id == uuid.UUID(user_id)
        ).values(**fields)
        await session.execute(stmt)
        await session.commit()


async def get_subscription_by_customer(customer_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription).where(
            Subscription.stripe_customer_id == customer_id
        )
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()
        if not sub:
            return None
        return {"user_id": str(sub.user_id), "tier": sub.tier}


# ──────────────────────────── Push Subscriptions ─────────────────────

async def save_push_subscription(
    user_id: str, endpoint: str, p256dh: str, auth_key: str,
) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == uuid.UUID(user_id),
                PushSubscription.endpoint == endpoint,
            )
        )
        if existing.scalar_one_or_none():
            return
        sub = PushSubscription(
            user_id=uuid.UUID(user_id),
            endpoint=endpoint,
            p256dh=p256dh,
            auth_key=auth_key,
        )
        session.add(sub)
        await session.commit()


async def get_push_subscriptions(user_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(PushSubscription).where(
            PushSubscription.user_id == uuid.UUID(user_id)
        )
        result = await session.execute(stmt)
        return [
            {
                "endpoint": s.endpoint,
                "p256dh": s.p256dh,
                "auth_key": s.auth_key,
            }
            for s in result.scalars().all()
        ]


async def delete_push_subscription(user_id: str, endpoint: str) -> None:
    async with AsyncSessionLocal() as session:
        stmt = delete(PushSubscription).where(
            PushSubscription.user_id == uuid.UUID(user_id),
            PushSubscription.endpoint == endpoint,
        )
        await session.execute(stmt)
        await session.commit()


# ──────────────────────────── Proactive Messages ─────────────────────

async def get_unconsumed_proactive_messages(user_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(ProactiveMessage).where(
            ProactiveMessage.user_id == uuid.UUID(user_id),
            ProactiveMessage.status == "pending",
        ).order_by(ProactiveMessage.priority)
        result = await session.execute(stmt)
        return [
            {
                "id": str(m.id),
                "content": m.content,
                "trigger_type": m.trigger_type,
                "created_at": m.created_at,
            }
            for m in result.scalars().all()
        ]


async def mark_proactive_messages_delivered(user_id: str, ids: list[str]) -> None:
    async with AsyncSessionLocal() as session:
        for msg_id in ids:
            stmt = update(ProactiveMessage).where(
                ProactiveMessage.id == uuid.UUID(msg_id),
                ProactiveMessage.user_id == uuid.UUID(user_id),
            ).values(status="delivered", delivered_at=datetime.now(timezone.utc))
            await session.execute(stmt)
        await session.commit()


async def save_proactive_message(
    user_id: str, content: str, trigger_type: str, priority: int = 5,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        msg = ProactiveMessage(
            user_id=uuid.UUID(user_id),
            content=content,
            trigger_type=trigger_type,
            priority=priority,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return {"id": str(msg.id), "content": msg.content, "trigger_type": msg.trigger_type}


# ──────────────────────────── Scheduled Actions ──────────────────────

async def get_pending_actions() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(ScheduledAction).where(
            ScheduledAction.status == "pending",
            ScheduledAction.run_at <= datetime.now(timezone.utc),
        ).order_by(ScheduledAction.run_at).limit(100)
        result = await session.execute(stmt)
        return [
            {
                "id": str(a.id),
                "user_id": str(a.user_id),
                "action_type": a.action_type,
                "payload": a.payload,
                "rrule": a.rrule,
            }
            for a in result.scalars().all()
        ]


async def claim_action(action_id: str) -> dict[str, Any] | None:
    """Atomically claim a pending action using UPDATE ... RETURNING to prevent races."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                UPDATE scheduled_actions
                SET status = 'executing'
                WHERE id = CAST(:aid AS uuid) AND status = 'pending'
                RETURNING id, user_id, action_type, payload, rrule
            """),
            {"aid": action_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        await session.commit()
        return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in dict(row).items()}


async def update_action_status(action_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        stmt = update(ScheduledAction).where(
            ScheduledAction.id == uuid.UUID(action_id)
        ).values(status=status)
        await session.execute(stmt)
        await session.commit()


async def save_scheduled_action(
    user_id: str,
    action_type: str,
    execute_at: datetime,
    payload: dict[str, Any] | None = None,
    rrule: str | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        action = ScheduledAction(
            user_id=uuid.UUID(user_id),
            action_type=action_type,
            payload=payload or {},
            run_at=execute_at,
            rrule=rrule,
        )
        session.add(action)
        await session.commit()
        await session.refresh(action)
        return {"id": str(action.id)}


async def mark_action_dispatched(action_id: str | uuid.UUID, message_id: str) -> None:
    async with AsyncSessionLocal() as session:
        aid = uuid.UUID(str(action_id)) if not isinstance(action_id, uuid.UUID) else action_id
        stmt = update(ScheduledAction).where(
            ScheduledAction.id == aid
        ).values(qstash_message_id=message_id)
        await session.execute(stmt)
        await session.commit()


# ──────────────────────────── Error Log ──────────────────────────────

async def save_error(
    source: str,
    error_type: str,
    error_message: str,
    stacktrace: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        err = ErrorLog(
            source=source,
            error_type=error_type,
            error_message=error_message,
            stacktrace=stacktrace,
            trace_id=trace_id,
            user_id=user_id,
        )
        session.add(err)
        await session.commit()


# ──────────────────────────── LLM Usage ──────────────────────────────

async def save_llm_usage(
    pipeline: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        usage = LLMUsage(
            pipeline=pipeline,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            trace_id=trace_id,
            user_id=user_id,
        )
        session.add(usage)
        await session.commit()


# ──────────────────────────── Account Deletion ───────────────────────

async def delete_user_data(user_id: str) -> dict[str, int]:
    """Cascade delete all user data across every table. GDPR-compliant.

    Deletes in FK-safe order: edges before nodes, everything before profiles.
    Also wipes operational tables (error_log, llm_usage) which store user_id
    as TEXT rather than FK — these have no RLS so must be explicitly cleaned.
    """
    uid = uuid.UUID(user_id)
    uid_str = str(uid)
    counts: dict[str, int] = {}
    async with AsyncSessionLocal() as session:
        # Tables with user_id as UUID FK — delete in dependency order
        for model, name in [
            (EventStream, "events"),
            (GraphEdge, "edges"),
            (GraphNode, "nodes"),
            (ProactiveMessage, "proactive"),
            (ScheduledAction, "actions"),
            (PushSubscription, "push_subs"),
            (Subscription, "subscriptions"),
        ]:
            stmt = delete(model).where(model.user_id == uid)
            result = await session.execute(stmt)
            counts[name] = result.rowcount

        # UserProfile PK is the user's auth.users id, not a separate user_id column
        result = await session.execute(
            delete(UserProfile).where(UserProfile.id == uid)
        )
        counts["profiles"] = result.rowcount

        # Operational tables store user_id as TEXT (no FK) — wipe for GDPR
        result = await session.execute(
            delete(ErrorLog).where(ErrorLog.user_id == uid_str)
        )
        counts["errors"] = result.rowcount

        result = await session.execute(
            delete(LLMUsage).where(LLMUsage.user_id == uid_str)
        )
        counts["llm_usage"] = result.rowcount

        await session.commit()
    return counts


# ──────────────────────────── Proactive Condition Helpers ─────────────

async def get_plate_items(user_id: str) -> list[dict[str, Any]]:
    """Get OPEN action items for the plate, urgency-ordered, top 7."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT node_id, content, deadline, deadline_type, created_at
            FROM vw_actionable
            WHERE user_id = :uid
            ORDER BY
                CASE WHEN deadline < NOW() THEN 0
                     WHEN deadline IS NOT NULL THEN 1
                     ELSE 2 END,
                deadline ASC NULLS LAST
            LIMIT 7
        """), {"uid": user_id})
        return [dict(r) for r in result.mappings().all()]


async def get_proactive_items(user_id: str, hours: int = 24) -> list[dict[str, Any]]:
    """Get OPEN action nodes with deadlines within N hours."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT node_id, content, deadline, deadline_type
            FROM vw_actionable
            WHERE user_id = :uid
              AND deadline IS NOT NULL
              AND deadline <= NOW() + (:hours || ' hours')::interval
              AND deadline >= NOW()
            ORDER BY deadline
        """), {"uid": user_id, "hours": str(hours)})
        return [dict(r) for r in result.mappings().all()]


async def get_slipped_items(user_id: str) -> list[dict[str, Any]]:
    """Get OPEN action nodes with past deadlines (soft or routine only, not hard)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT node_id, content, deadline
            FROM vw_actionable
            WHERE user_id = :uid
              AND deadline IS NOT NULL
              AND deadline < NOW()
              AND deadline_type IN ('soft', 'routine')
            ORDER BY deadline DESC
            LIMIT 10
        """), {"uid": user_id})
        return [dict(r) for r in result.mappings().all()]


async def get_recently_done_count(user_id: str, hours: int = 24) -> int:
    """Count nodes transitioned to DONE status within N hours."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT COUNT(*) as cnt
            FROM event_stream
            WHERE user_id = :uid              AND event_type = 'StatusUpdated'
              AND payload->>'new_status' = 'DONE'
              AND created_at >= NOW() - (:hours || ' hours')::interval
        """), {"uid": user_id, "hours": str(hours)})
        row = result.mappings().first()
        return int(row["cnt"]) if row else 0


async def get_deadline_calendar(user_id: str) -> dict[str, list[dict[str, Any]]]:
    """Get deadline items grouped by today/tomorrow/this_week from vw_timeline."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT node_id, content, deadline, deadline_type,
                CASE
                    WHEN deadline::date = CURRENT_DATE THEN 'today'
                    WHEN deadline::date = CURRENT_DATE + 1 THEN 'tomorrow'
                    ELSE 'this_week'
                END as period
            FROM vw_timeline
            WHERE user_id = :uid
              AND deadline::timestamptz >= NOW()
              AND deadline::timestamptz < NOW() + interval '7 days'
            ORDER BY deadline::timestamptz
        """), {"uid": user_id})
        rows = [dict(r) for r in result.mappings().all()]

    calendar: dict[str, list[dict[str, Any]]] = {"today": [], "tomorrow": [], "this_week": []}
    for row in rows:
        period = row.pop("period", "this_week")
        if period in calendar:
            calendar[period].append(row)
    return calendar


async def get_metric_summary(user_id: str) -> list[dict[str, Any]]:
    """Get latest metric values grouped by metric name from vw_metrics."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT DISTINCT ON (metric_name)
                metric_name,
                value AS latest_value,
                unit,
                event_time::date::text AS latest_date
            FROM vw_metrics
            WHERE user_id = :uid
            ORDER BY metric_name, event_time DESC
        """), {"uid": user_id})
        return [dict(r) for r in result.mappings().all()]
