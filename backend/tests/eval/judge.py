"""LLM-as-judge: evaluates agent responses against criteria using Ollama."""

import asyncio
import json
import os
from typing import Any

from openai import AsyncOpenAI

_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "qwen2.5-coder:32b")

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0

_JUDGE_SYSTEM = """You are an eval judge for Unspool, an AI personal assistant.
You evaluate whether an AI response meets a specific criterion.

You will receive:
- The conversation (user messages)
- The AI's response
- One specific criterion to evaluate

Return a JSON object with exactly two fields:
- "pass": true or false
- "reason": one sentence explaining your judgment

Be strict. If the criterion says "must not" and the response does it even slightly, fail it.
If the criterion says "must" and the response doesn't clearly do it, fail it."""

_JUDGE_USER = """Conversation:
{conversation}

AI Response:
{response}

Criterion: {criterion}

Return JSON: {{"pass": true/false, "reason": "..."}}"""


async def judge_criterion(
    conversation: list[dict[str, str]],
    response: str,
    criterion: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Evaluate a single criterion against the response.

    Returns {"pass": bool, "reason": str}.
    """
    client = AsyncOpenAI(base_url=f"{_OLLAMA_URL}/v1", api_key="ollama")
    judge_model = model or _JUDGE_MODEL

    conv_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in conversation)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = await client.chat.completions.create(
                model=judge_model,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {
                        "role": "user",
                        "content": _JUDGE_USER.format(
                            conversation=conv_text,
                            response=response,
                            criterion=criterion,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            parsed = json.loads(result.choices[0].message.content or "{}")
            return {
                "pass": bool(parsed.get("pass", False)),
                "reason": parsed.get("reason", "no reason provided"),
            }
        except (json.JSONDecodeError, IndexError):
            return {"pass": False, "reason": "judge returned invalid JSON"}
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))

    return {"pass": False, "reason": f"judge API error: {last_exc}"}


async def judge_scenario(
    conversation: list[dict[str, str]],
    response: str,
    response_must: list[str],
    response_must_not: list[str],
    model: str | None = None,
) -> "JudgeResult":
    """Evaluate all criteria for a scenario.

    Returns JudgeResult with per-criterion results and aggregate score.
    """
    results: list[dict[str, Any]] = []

    for criterion in response_must:
        verdict = await judge_criterion(
            conversation, response, f"The response MUST: {criterion}", model
        )
        results.append(
            {
                "type": "must",
                "criterion": criterion,
                **verdict,
            }
        )

    for criterion in response_must_not:
        verdict = await judge_criterion(
            conversation, response, f"The response MUST NOT: {criterion}", model
        )
        results.append(
            {
                "type": "must_not",
                "criterion": criterion,
                **verdict,
            }
        )

    return JudgeResult(results=results)


class JudgeResult:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r["pass"])

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r["pass"])

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def score(self) -> float:
        if not self.results:
            return 1.0
        return self.passed / self.total

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [r for r in self.results if not r["pass"]]

    def summary(self) -> str:
        lines = [f"Score: {self.passed}/{self.total} ({self.score:.0%})"]
        for f in self.failures:
            lines.append(f"  FAIL [{f['type']}] {f['criterion']}: {f['reason']}")
        return "\n".join(lines)
