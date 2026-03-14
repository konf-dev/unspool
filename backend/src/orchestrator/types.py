from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Pipeline config models (extra="forbid" to catch typos) ---


class Step(BaseModel, extra="forbid"):
    id: str
    type: Literal["llm_call", "tool_call", "query", "operation", "branch", "transform"]
    prompt: str | None = None
    model: str | None = None
    tool: str | None = None
    query: str | None = None
    operation: str | None = None
    input: dict[str, str | None] | None = None
    output_schema: str | None = None
    stream: bool = False
    conditions: list[dict[str, Any]] | None = None
    transform: str | None = None
    retry: dict[str, Any] | None = None


class PostProcessingJob(BaseModel, extra="forbid"):
    job: str
    delay: str = "0s"


class Pipeline(BaseModel, extra="forbid"):
    name: str
    description: str = ""
    steps: list[Step]
    post_processing: list[PostProcessingJob] | None = None


# --- Runtime types (mutable, so no extra="forbid") ---


class Context(BaseModel):
    user_id: str
    trace_id: str
    user_message: str
    profile: dict[str, Any] | None = None
    open_items: list[dict[str, Any]] | None = None
    recent_messages: list[dict[str, Any]] | None = None
    urgent_items: list[dict[str, Any]] | None = None
    memories: list[dict[str, Any]] | None = None
    entities: list[dict[str, Any]] | None = None
    calendar_events: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    post_processing_jobs: list[PostProcessingJob] | None = None


class StepResult(BaseModel):
    step_id: str
    output: Any
    latency_ms: float
    tokens_used: int = 0


# --- LLM output schemas (extra="allow" — LLMs may add fields) ---


class IntentClassification(BaseModel, extra="allow"):
    intent: str = "conversation"
    confidence: float = 0.5
    sub_intent: str | None = None


class ExtractedItem(BaseModel, extra="allow"):
    raw_text: str = ""
    interpreted_action: str = ""
    deadline_type: str = "none"
    deadline_at: str | None = None
    urgency_score: float = 0.0
    energy_estimate: str = "medium"


class ItemExtraction(BaseModel, extra="allow"):
    items: list[ExtractedItem] = Field(default_factory=list)
    non_actionable_notes: list[str] = Field(default_factory=list)


class QueryAnalysis(BaseModel, extra="allow"):
    search_type: str = "general"
    entity: str | None = None
    timeframe: str | None = None
    sources: list[str] = Field(default_factory=lambda: ["items", "memories"])
    text_query: str | None = None
    status_filter: str = "all"
    limit: int = 10


class EmotionalDetection(BaseModel, extra="allow"):
    level: str = "low"
    needs_support: bool = False
    reasoning: str | None = None


class ImplicitItems(BaseModel, extra="allow"):
    items: list[ExtractedItem] = Field(default_factory=list)


# Registry: maps output_schema string in pipeline YAML → Pydantic model
OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "IntentClassification": IntentClassification,
    "ItemExtraction": ItemExtraction,
    "QueryAnalysis": QueryAnalysis,
    "EmotionalDetection": EmotionalDetection,
    "ImplicitItems": ImplicitItems,
}
