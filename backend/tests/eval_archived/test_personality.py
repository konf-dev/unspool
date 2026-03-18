import pytest

from tests.eval.client import EvalClient
from tests.eval.fixtures import InMemoryStore, eval_items
from tests.eval.judge import judge_response
from tests.eval.loader import load_golden_cases
from tests.eval.types import AssertionResult, Assertion, CaseResult

pytestmark = pytest.mark.eval


def _check_assertion(assertion: Assertion, response: str) -> AssertionResult:
    if assertion.type == "contains":
        passed = assertion.value.lower() in response.lower()
        return AssertionResult(
            assertion=assertion, passed=passed, actual=response[:200]
        )
    if assertion.type == "not_contains":
        passed = assertion.value.lower() not in response.lower()
        return AssertionResult(
            assertion=assertion, passed=passed, actual=response[:200]
        )
    if assertion.type == "max_sentences":
        import re

        sentences = len(re.split(r"[.!?]+", response.strip()))
        passed = sentences <= assertion.value
        return AssertionResult(assertion=assertion, passed=passed, actual=sentences)
    return AssertionResult(
        assertion=assertion, passed=False, actual=None, detail="unknown type"
    )


@pytest.mark.asyncio
class TestPersonality:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("personality_constraints.yaml", tag_filter=eval_tag)

    async def test_personality_constraints(
        self,
        cases: list,
        eval_client: EvalClient,
        eval_results: list[CaseResult],
    ) -> None:
        for case in cases:
            store = InMemoryStore(initial_items=eval_items())
            try:
                resp = await eval_client.send_message(case.message, store=store)
            except Exception as e:
                eval_results.append(
                    CaseResult(case_id=case.id, passed=False, error=str(e))
                )
                continue

            assertion_results = [
                _check_assertion(a, resp.response_text) for a in case.assertions
            ]

            judge_results = []
            for criterion in case.judge_criteria:
                jr = await judge_response(criterion, case.message, resp.response_text)
                judge_results.append(jr)

            passed = all(ar.passed for ar in assertion_results) and all(
                jr.passed for jr in judge_results
            )

            eval_results.append(
                CaseResult(
                    case_id=case.id,
                    passed=passed,
                    response=resp.response_text,
                    intent=resp.intent,
                    latency_ms=resp.latency_ms,
                    assertion_results=assertion_results,
                    judge_results=judge_results,
                    trace_id=resp.trace_id,
                )
            )

        failed = [
            r
            for r in eval_results
            if not r.passed and r.case_id.startswith("personality_")
        ]
        if failed:
            details = []
            for r in failed:
                a_fails = [ar for ar in r.assertion_results if not ar.passed]
                j_fails = [jr for jr in r.judge_results if not jr.passed]
                details.append(f"  {r.case_id}: assertions={a_fails}, judge={j_fails}")
            pytest.fail("Personality failures:\n" + "\n".join(details))


@pytest.mark.asyncio
class TestEmotionalDetection:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("emotional_detection.yaml", tag_filter=eval_tag)

    async def test_emotional_calibration(
        self,
        cases: list,
        eval_client: EvalClient,
        eval_results: list[CaseResult],
    ) -> None:
        for case in cases:
            store = InMemoryStore(initial_items=eval_items())
            try:
                resp = await eval_client.send_message(case.message, store=store)
            except Exception as e:
                eval_results.append(
                    CaseResult(case_id=case.id, passed=False, error=str(e))
                )
                continue

            judge_results = []
            for criterion in case.judge_criteria:
                jr = await judge_response(criterion, case.message, resp.response_text)
                judge_results.append(jr)

            passed = all(jr.passed for jr in judge_results)

            eval_results.append(
                CaseResult(
                    case_id=case.id,
                    passed=passed,
                    response=resp.response_text,
                    intent=resp.intent,
                    latency_ms=resp.latency_ms,
                    judge_results=judge_results,
                    trace_id=resp.trace_id,
                )
            )

        failed = [
            r for r in eval_results if not r.passed and r.case_id.startswith("emotion_")
        ]
        if failed:
            details = []
            for r in failed:
                j_fails = [jr for jr in r.judge_results if not jr.passed]
                details.append(
                    f"  {r.case_id}: {[(j.criterion, j.score) for j in j_fails]}"
                )
            pytest.fail("Emotional detection failures:\n" + "\n".join(details))
