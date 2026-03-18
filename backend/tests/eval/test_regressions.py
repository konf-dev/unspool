import pytest

from tests.eval.client import EvalClient
from tests.eval.fixtures import InMemoryStore, eval_items
from tests.eval.judge import judge_response
from tests.eval.loader import load_golden_cases
from tests.eval.types import AssertionResult, Assertion, CaseResult

pytestmark = pytest.mark.eval


def _check_assertion(
    assertion: Assertion, response: str, store: InMemoryStore
) -> AssertionResult:
    if assertion.field == "response":
        actual = response
    elif assertion.field == "item_count":
        actual = len(store.items)
    elif assertion.field.startswith("items["):
        import re

        m = re.match(r"items\[(\d+)\]\.(\w+)", assertion.field)
        if m:
            idx, attr = int(m.group(1)), m.group(2)
            actual = store.items[idx].get(attr) if idx < len(store.items) else None
        else:
            actual = None
    else:
        actual = None

    if assertion.type == "contains":
        passed = assertion.value.lower() in str(actual).lower()
    elif assertion.type == "not_contains":
        passed = assertion.value.lower() not in str(actual).lower()
    elif assertion.type == "equals":
        passed = str(actual) == str(assertion.value)
    elif assertion.type == "min_count":
        passed = (actual or 0) >= assertion.value
    elif assertion.type == "not_null":
        passed = actual is not None
    elif assertion.type == "max_sentences":
        import re as re_mod

        sentences = len(re_mod.split(r"[.!?]+", str(actual).strip()))
        passed = sentences <= assertion.value
        actual = sentences
    else:
        passed = False

    return AssertionResult(assertion=assertion, passed=passed, actual=actual)


@pytest.mark.asyncio
class TestRegressions:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("known_bugs.yaml", tag_filter=eval_tag)

    async def test_known_bugs(
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
                _check_assertion(a, resp.response_text, store) for a in case.assertions
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
            r for r in eval_results if not r.passed and r.case_id.startswith("bug_")
        ]
        if failed:
            details = []
            for r in failed:
                a_fails = [ar for ar in r.assertion_results if not ar.passed]
                j_fails = [jr for jr in r.judge_results if not jr.passed]
                details.append(f"  {r.case_id}: assertions={a_fails}, judge={j_fails}")
            pytest.fail("Regression failures:\n" + "\n".join(details))
