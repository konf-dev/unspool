from typing import Any

from pydantic import BaseModel, Field


# --- gate.yaml ---


class TierLimit(BaseModel, extra="forbid"):
    daily_messages: int
    message: str = "You've reached your daily message limit."


class RateLimits(BaseModel, extra="forbid"):
    free: TierLimit
    paid: TierLimit


class GateConfig(BaseModel, extra="forbid"):
    rate_limits: RateLimits


# --- scoring.yaml ---


class DecayHardRamp(BaseModel, extra="forbid"):
    overdue: float
    within_24h_base: float
    within_24h_divisor: float
    within_72h_base: float
    within_72h_divisor: float


class DecayConfig(BaseModel, extra="forbid"):
    soft_decay_factor: float
    auto_expire_days: int
    auto_expire_threshold: float
    hard_ramp: DecayHardRamp


class MomentumConfig(BaseModel, extra="forbid"):
    lookback_hours: int
    on_a_roll_threshold: int


class PickNextConfig(BaseModel, extra="forbid"):
    boost_hard_deadline: float
    boost_soft_deadline: float
    boost_low_energy: float
    boost_medium_energy: float
    boost_never_surfaced: float


class RescheduleConfig(BaseModel, extra="forbid"):
    urgency_decay_factor: float
    nudge_delay: dict[str, int]


class MatchingConfig(BaseModel, extra="forbid"):
    min_similarity: float
    substring_boost: float


class NotificationsConfig(BaseModel, extra="forbid"):
    quiet_hours_start: int
    quiet_hours_end: int
    deadline_window_hours: int
    title: str
    body_single: str
    body_multiple: str


class ScoringConfig(BaseModel, extra="forbid"):
    decay: DecayConfig
    momentum: MomentumConfig
    pick_next: PickNextConfig
    reschedule: RescheduleConfig
    matching: MatchingConfig
    notifications: NotificationsConfig


# --- proactive.yaml ---


class ProactiveTrigger(BaseModel, extra="forbid"):
    enabled: bool
    description: str
    condition: str
    params: dict[str, Any]
    prompt: str
    priority: int


class ProactiveConfig(BaseModel, extra="forbid"):
    triggers: dict[str, ProactiveTrigger]
    metadata_type: str = "proactive"


# --- jobs.yaml ---


class CronJobDef(BaseModel, extra="forbid"):
    schedule: str
    schedule_id: str


class JobsConfig(BaseModel, extra="forbid"):
    cron_jobs: dict[str, CronJobDef]
    dispatch_map: dict[str, str] = Field(default_factory=dict)


# --- intents.yaml ---


class IntentDef(BaseModel, extra="forbid"):
    description: str
    pipeline: str


class IntentsConfig(BaseModel, extra="forbid"):
    intents: dict[str, IntentDef]
    fallback_intent: str = "conversation"
    classification_model: str | None = None


# --- context_rules.yaml ---


class ContextRule(BaseModel, extra="forbid"):
    load: list[str]
    optional: list[str] = Field(default_factory=list)


class ContextDefaults(BaseModel, extra="forbid"):
    recent_messages_limit: int = 20
    open_items_limit: int = 50
    memories_limit: int = 5


class ContextRulesConfig(BaseModel, extra="forbid"):
    rules: dict[str, ContextRule]
    defaults: ContextDefaults


# --- patterns.yaml ---


class AnalysisDef(BaseModel, extra="forbid"):
    type: str
    enabled: bool
    description: str
    prompt: str | None = None
    min_data_days: int | None = None
    lookback_days: int | None = None
    confidence_threshold: float | None = None
    min_memories: int | None = None
    run_on: str | None = None


class PatternsConfig(BaseModel, extra="forbid"):
    analyses: dict[str, AnalysisDef]
    output_field: str = "patterns"


# --- graph.yaml ---


class GraphIngestConfig(BaseModel, extra="forbid"):
    quick_model: str | None = None
    quick_max_nodes: int = 10
    deep_model: str | None = None
    recent_nodes_context: int = 30


class GraphRetrievalConfig(BaseModel, extra="forbid"):
    default_triggers: list[str] = Field(default_factory=list)
    graph_walk_hops: int = 1
    max_subgraph_nodes: int = 50
    semantic_limit: int = 15
    temporal_window_hours: int = 48
    recent_limit: int = 10
    suppression_window_hours: int = 24


class GraphSerializationConfig(BaseModel, extra="forbid"):
    max_context_tokens: int = 2000


class GraphEvolutionConfig(BaseModel, extra="forbid"):
    embedding_model: str = "text-embedding-3-small"
    similarity_threshold: float = 0.8
    dedup_threshold: float = 0.9
    edge_decay_factor: float = 0.99
    edge_decay_min: float = 0.01
    contradiction_threshold: float = 0.9
    shortcut_co_retrieval_count: int = 3


class GraphFeedbackConfig(BaseModel, extra="forbid"):
    async_detection: bool = True


class GraphConfigModel(BaseModel, extra="forbid"):
    ingest: GraphIngestConfig = Field(default_factory=GraphIngestConfig)
    retrieval: GraphRetrievalConfig = Field(default_factory=GraphRetrievalConfig)
    serialization: GraphSerializationConfig = Field(
        default_factory=GraphSerializationConfig
    )
    evolution: GraphEvolutionConfig = Field(default_factory=GraphEvolutionConfig)
    feedback: GraphFeedbackConfig = Field(default_factory=GraphFeedbackConfig)
    shadow_mode: bool = True


# --- triggers.yaml ---


class TriggerDefModel(BaseModel, extra="forbid"):
    enabled: bool = True
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class TriggersConfigModel(BaseModel, extra="forbid"):
    triggers: dict[str, TriggerDefModel] = Field(default_factory=dict)


# Registry: maps config file name → Pydantic model
CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "gate": GateConfig,
    "scoring": ScoringConfig,
    "proactive": ProactiveConfig,
    "jobs": JobsConfig,
    "intents": IntentsConfig,
    "context_rules": ContextRulesConfig,
    "patterns": PatternsConfig,
    "graph": GraphConfigModel,
    "triggers": TriggersConfigModel,
}
