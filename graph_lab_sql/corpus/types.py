"""Types for corpus replay — extended with temporal metrics."""

from pydantic import BaseModel, Field


class CorpusMessage(BaseModel):
    id: str
    persona: str
    day: int
    message_index: int
    time_of_day: str
    energy: str
    mood: str
    content: str
    scenario_tag: str | None = None
    generation_model: str


class DayMarker(BaseModel):
    id: str
    persona: str
    day: int
    type: str = "day_marker"
    skipped: bool = False


class ScenarioStep(BaseModel):
    instruction: str
    delay_messages: list[int] = Field(default_factory=lambda: [0, 0])


class ScenarioDef(BaseModel):
    id: str
    description: str
    inject_at: dict = Field(default_factory=dict)
    steps: list[ScenarioStep] = Field(default_factory=list)


class ScenarioFile(BaseModel):
    scenarios: list[ScenarioDef] = Field(default_factory=list)


class ScheduledScenario(BaseModel):
    scenario_id: str
    persona: str
    start_day: int
    current_step: int = 0
    messages_until_next: int = 0
    steps: list[ScenarioStep] = Field(default_factory=list)


class ReplayTurn(BaseModel):
    corpus_id: str
    day: int
    user_message: str
    unspool_response: str
    ingest_ms: float = 0
    retrieval_ms: float = 0
    reasoning_ms: float = 0
    feedback_ms: float = 0
    total_ms: float = 0
    graph_stats: dict = Field(default_factory=dict)
    # Corpus ground truth
    time_of_day: str = ""
    energy: str = ""
    mood: str = ""
    scenario_tag: str | None = None
    # Temporal metrics (new)
    corrections_applied: int = 0
    edges_invalidated: int = 0


class ScenarioScore(BaseModel):
    score: float = 5.0
    reasoning: str = ""


class ReplayEvaluation(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0
    assessment: str = ""
    scenario_scores: dict[str, ScenarioScore] = Field(default_factory=dict)


class ReplayResult(BaseModel):
    persona: str
    corpus_path: str
    user_id: str = ""
    turns: list[ReplayTurn] = Field(default_factory=list)
    skipped_days: int = 0
    total_messages: int = 0
    evolutions_run: int = 0
    graph_config: str | None = None
    final_graph_stats: dict = Field(default_factory=dict)
    temporal_stats: dict = Field(default_factory=dict)
    evaluation: ReplayEvaluation = Field(default_factory=ReplayEvaluation)


class CorpusConfig(BaseModel):
    default_model: str = "qwen2.5:7b"
    persona_models: dict[str, str] = Field(default_factory=dict)
    persona_ollama_urls: dict[str, str] = Field(default_factory=dict)
    concurrency: int = 2
    default_days: int = 90
    temperature: float = 0.9
    hardcoded_messages: dict[str, list[str]] = Field(default_factory=dict)
    open_ended: dict[str, float] = Field(default_factory=dict)
    max_retries: int = 2
