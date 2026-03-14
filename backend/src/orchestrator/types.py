from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    id: str
    type: str  # llm_call | tool_call | query | operation | branch | transform
    prompt: str | None = None
    model: str | None = None
    tool: str | None = None
    query: str | None = None
    operation: str | None = None
    input: dict[str, str] | None = None
    output_schema: str | None = None
    stream: bool = False
    conditions: list[dict[str, Any]] | None = None
    transform: str | None = None
    retry: dict[str, Any] | None = None


@dataclass
class PostProcessingJob:
    job: str
    delay: str


@dataclass
class Pipeline:
    name: str
    description: str
    steps: list[Step]
    post_processing: list[PostProcessingJob] | None = None


@dataclass
class Context:
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
    extra: dict[str, Any] = field(default_factory=dict)
    post_processing_jobs: list["PostProcessingJob"] | None = None


@dataclass
class StepResult:
    step_id: str
    output: Any
    latency_ms: float
    tokens_used: int = 0
