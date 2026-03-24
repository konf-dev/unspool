import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from src.core.database import Base


class EventStream(Base):
    __tablename__ = "event_stream"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_event_stream_user_id_created_at", "user_id", "created_at"),
    )


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    content = Column(String, nullable=False)
    node_type = Column(String, nullable=False, index=True)
    embedding = Column(Vector(768))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type = Column(String, nullable=False, index=True)
    weight = Column(Float, default=1.0)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_graph_edge"),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True)
    display_name = Column(Text)
    timezone = Column(Text, default="UTC")
    tone_preference = Column(Text, default="casual")
    length_preference = Column(Text, default="medium")
    pushiness_preference = Column(Text, default="gentle")
    uses_emoji = Column(Boolean, default=False)
    primary_language = Column(Text, default="en")
    patterns = Column(JSONB, default=dict)
    last_interaction_at = Column(DateTime(timezone=True))
    last_proactive_at = Column(DateTime(timezone=True))
    notification_sent_today = Column(Boolean, default=False)
    feed_token = Column(Text)
    email_alias = Column(Text, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    tier = Column(Text, nullable=False, default="free")
    stripe_customer_id = Column(Text)
    stripe_subscription_id = Column(Text)
    status = Column(Text, nullable=False, default="active")
    current_period_end = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    endpoint = Column(Text, nullable=False)
    p256dh = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", name="uq_push_sub"),
    )


class ProactiveMessage(Base):
    __tablename__ = "proactive_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    trigger_type = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    priority = Column(Integer, default=5)
    status = Column(Text, nullable=False, default="pending")
    expires_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduledAction(Base):
    __tablename__ = "scheduled_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    action_type = Column(Text, nullable=False)
    payload = Column(JSONB, default=dict)
    run_at = Column(DateTime(timezone=True), nullable=False)
    rrule = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    qstash_message_id = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ErrorLog(Base):
    __tablename__ = "error_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(Text)
    user_id = Column(Text)
    source = Column(Text, nullable=False)
    error_type = Column(Text, nullable=False)
    error_message = Column(Text)
    stacktrace = Column(Text)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(Text)
    user_id = Column(Text)
    pipeline = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
