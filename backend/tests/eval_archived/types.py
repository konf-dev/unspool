from typing import Any, Literal

from pydantic import BaseModel, Field


class Assertion(BaseModel):
    type: Literal[
        "contains",
        "not_contains",
        "equals",
        "max_sentences",
        "min_count",
        "max_value",
        "not_null",
    ]
    field: str
    value: Any = None


class JudgeCriterion(BaseModel):
    name: str
    prompt: str
    pass_threshold: float = 7.0


class GoldenCase(BaseModel):
    id: str
    category: str
    message: str
    setup_messages: list[dict[str, str]] = Field(default_factory=list)
    expected_intent: str | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    judge_criteria: list[JudgeCriterion] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AssertionResult(BaseModel):
    assertion: Assertion
    passed: bool
    actual: Any = None
    detail: str = ""


class JudgeResult(BaseModel):
    criterion: str
    score: float
    reasoning: str
    passed: bool


class CaseResult(BaseModel):
    case_id: str
    passed: bool
    response: str = ""
    intent: str | None = None
    confidence: float | None = None
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    judge_results: list[JudgeResult] = Field(default_factory=list)
    trace_id: str | None = None
    error: str | None = None


class CategorySummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0


class PerformanceEntry(BaseModel):
    pipeline: str
    p50_ms: float
    p95_ms: float
    samples: int


class RegressionDiff(BaseModel):
    new_failures: list[str] = Field(default_factory=list)
    new_passes: list[str] = Field(default_factory=list)
    latency_regressions: list[str] = Field(default_factory=list)
    score_drops: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    timestamp: str
    git_sha: str
    target: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    categories: dict[str, CategorySummary] = Field(default_factory=dict)
    performance: list[PerformanceEntry] = Field(default_factory=list)
    results: list[CaseResult] = Field(default_factory=list)
    regression_diff: RegressionDiff | None = None
