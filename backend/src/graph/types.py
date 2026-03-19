"""Pydantic models for graph memory — production types."""

from datetime import datetime

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    user_id: str
    content: str
    node_type: str | None = None
    embedding: list[float] | None = None
    status: str = "active"
    source_message_id: str | None = None
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
    source_message_id: str | None = None


class TriggerResult(BaseModel):
    trigger_name: str
    node_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ActiveSubgraph(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    trigger_results: list[TriggerResult] = Field(default_factory=list)


# --- Correction model (bi-temporal) ---


class Correction(BaseModel):
    target_content: str
    old_value: str
    new_value: str
    correction_type: str = "explicit"


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


class FeedbackResult(BaseModel):
    surfaced_node_ids: list[str] = Field(default_factory=list)
    completions_acknowledged: list[str] = Field(default_factory=list)
    suppressions: list[str] = Field(default_factory=list)


# --- Config models ---


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
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    serialization: SerializationConfig = Field(default_factory=SerializationConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    shadow_mode: bool = True


class TriggerDef(BaseModel):
    enabled: bool = True
    type: str
    params: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class TriggersConfig(BaseModel):
    triggers: dict[str, TriggerDef] = Field(default_factory=dict)
