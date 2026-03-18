"""Pydantic models for graph_lab_sql — extended with bi-temporal support."""

from datetime import datetime

from pydantic import BaseModel, Field


class StreamEntry(BaseModel):
    id: str
    user_id: str
    source: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class Node(BaseModel):
    id: str
    user_id: str
    content: str
    node_type: str | None = None
    embedding: list[float] | None = None
    status: str = "active"
    source_stream_id: str | None = None
    created_at: datetime
    last_activated_at: datetime


class Edge(BaseModel):
    id: str
    user_id: str
    from_node_id: str
    to_node_id: str
    relation_type: str | None = None
    strength: float = 1.0
    valid_from: datetime
    valid_until: datetime | None = None
    recorded_at: datetime
    decay_exempt: bool = False
    source_stream_id: str | None = None


class TriggerResult(BaseModel):
    trigger_name: str
    node_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ActiveSubgraph(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    trigger_results: list[TriggerResult] = Field(default_factory=list)


# --- Correction model (new for bi-temporal) ---


class Correction(BaseModel):
    target_content: str
    old_value: str
    new_value: str
    correction_type: str = "explicit"  # explicit, implicit, retroactive


# --- Temporal stats ---


class TemporalStats(BaseModel):
    total_edges: int = 0
    current_edges: int = 0
    invalidated_edges: int = 0
    corrections_applied: int = 0
    decay_exempt_edges: int = 0


# --- Ingest LLM output models ---


class IngestNode(BaseModel):
    content: str
    existing_match: str | None = None


class IngestEdge(BaseModel):
    from_content: str = Field(alias="from")
    to_content: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class IngestEdgeUpdate(BaseModel):
    from_content: str = Field(alias="from")
    to_content: str = Field(alias="to")
    new_strength: float

    model_config = {"populate_by_name": True}


class IngestOutput(BaseModel):
    nodes: list[IngestNode] = Field(default_factory=list)
    edges: list[IngestEdge] = Field(default_factory=list)
    edge_updates: list[IngestEdgeUpdate] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)


# --- Evolution LLM output models ---


class MergeSuggestion(BaseModel):
    keep_node_id: str
    remove_node_id: str
    reason: str


class NewEdgeSuggestion(BaseModel):
    from_node_id: str
    to_node_id: str
    reason: str


class ContradictionFlag(BaseModel):
    node_id_a: str
    node_id_b: str
    description: str


class RefinementSuggestion(BaseModel):
    node_id: str
    new_content: str
    reason: str


class EvolutionOutput(BaseModel):
    merges: list[MergeSuggestion] = Field(default_factory=list)
    new_edges: list[NewEdgeSuggestion] = Field(default_factory=list)
    contradictions: list[ContradictionFlag] = Field(default_factory=list)
    refinements: list[RefinementSuggestion] = Field(default_factory=list)


class EvolutionResult(BaseModel):
    nodes_merged: int = 0
    edges_created: int = 0
    edges_decayed: int = 0
    edges_pruned: int = 0
    embeddings_generated: int = 0
    contradictions_found: int = 0
    edges_invalidated: int = 0


# --- Feedback models ---


class FeedbackCommitment(BaseModel):
    type: str
    trigger_at: datetime | None = None
    about_node_ids: list[str] = Field(default_factory=list)
    message_hint: str = ""


class FeedbackResult(BaseModel):
    surfaced_node_ids: list[str] = Field(default_factory=list)
    completions_acknowledged: list[str] = Field(default_factory=list)
    commitments_made: list[FeedbackCommitment] = Field(default_factory=list)
    suppressions: list[str] = Field(default_factory=list)


# --- Simulation models ---


class TurnPerf(BaseModel):
    ingest_ms: float = 0
    retrieval_ms: float = 0
    reasoning_ms: float = 0
    feedback_ms: float = 0
    total_ms: float = 0
    user_sim_ms: float = 0


class SimulationTurn(BaseModel):
    day: int
    time_of_day: str
    user_message: str
    unspool_response: str
    user_state: dict = Field(default_factory=dict)
    graph_stats: dict = Field(default_factory=dict)
    perf: TurnPerf = Field(default_factory=TurnPerf)


class EvaluationResult(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0
    assessment: str = ""
    missed_items: list[str] = Field(default_factory=list)
    false_surfacings: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    persona: str
    turns: list[SimulationTurn] = Field(default_factory=list)
    evaluation: EvaluationResult = Field(default_factory=EvaluationResult)
    final_graph_stats: dict = Field(default_factory=dict)


# --- Config models ---


class DatabaseConfig(BaseModel):
    dsn: str | None = None
    min_pool_size: int = 2
    max_pool_size: int = 10


class IngestConfig(BaseModel):
    quick_model: str | None = None
    quick_max_nodes: int = 10
    deep_model: str | None = None
    recent_nodes_context: int = 30


class RetrievalConfig(BaseModel):
    default_triggers: list[str] = Field(
        default_factory=lambda: [
            "semantic",
            "temporal",
            "open_items",
            "recent",
            "suppression",
        ]
    )
    graph_walk_hops: int = 1
    max_subgraph_nodes: int = 50
    semantic_limit: int = 15
    temporal_window_hours: int = 48
    recent_limit: int = 10
    suppression_window_hours: int = 24


class ReasoningConfig(BaseModel):
    model: str | None = None
    system_prompt: str = "system.md"
    max_recent_messages: int = 6
    temperature: float = 0.7
    session_gap_hours: int = 4


class SerializationConfig(BaseModel):
    max_context_tokens: int = 2000


class EvolutionConfig(BaseModel):
    embedding_model: str = "text-embedding-3-small"
    similarity_threshold: float = 0.8
    dedup_threshold: float = 0.9
    edge_decay_factor: float = 0.99
    edge_decay_min: float = 0.01
    contradiction_threshold: float = 0.9
    shortcut_co_retrieval_count: int = 3


class FeedbackConfig(BaseModel):
    async_detection: bool = True


class GraphConfig(BaseModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)
    serialization: SerializationConfig = Field(default_factory=SerializationConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)


class TriggerParams(BaseModel):
    model_config = {"extra": "allow"}


class TriggerDef(BaseModel):
    enabled: bool = True
    type: str
    params: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class TriggersConfig(BaseModel):
    triggers: dict[str, TriggerDef] = Field(default_factory=dict)


class PersonaRelationship(BaseModel):
    name: str
    type: str | None = None
    location: str | None = None
    dynamic: str | None = None
    details: str | None = None

    model_config = {"extra": "allow"}


class PersonaSimulation(BaseModel):
    duration_days: int = 30
    messages_per_day: list[int] = Field(default_factory=lambda: [1, 5])
    bad_day_probability: float = 0.2
    skip_day_probability: float = 0.15


class PersonaConfig(BaseModel):
    name: str
    age: int
    background: str
    personality: dict
    current_life: dict
    behavior_patterns: list[str] = Field(default_factory=list)
    simulation: PersonaSimulation = Field(default_factory=PersonaSimulation)

    model_config = {"extra": "allow"}
