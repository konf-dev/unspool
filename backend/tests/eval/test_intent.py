import pytest

from tests.eval.loader import load_golden_cases
from tests.eval.types import AssertionResult, Assertion, CaseResult

pytestmark = pytest.mark.eval


@pytest.mark.asyncio
class TestIntentClassification:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("intent_classification.yaml", tag_filter=eval_tag)

    async def test_intent_classification(
        self,
        cases: list,
        eval_results: list[CaseResult],
    ) -> None:
        from src.orchestrator.intent import classify_intent
        from src.orchestrator.types import Context

        for case in cases:
            ctx = Context(
                user_id="eval-user-001",
                trace_id="eval-trace",
                user_message=case.message,
            )

            try:
                intent_name, _pipeline, confidence = await classify_intent(
                    case.message, ctx
                )
            except Exception as e:
                eval_results.append(
                    CaseResult(
                        case_id=case.id,
                        passed=False,
                        error=str(e),
                    )
                )
                continue

            passed = intent_name == case.expected_intent

            assertion_results = [
                AssertionResult(
                    assertion=Assertion(
                        type="equals", field="intent", value=case.expected_intent
                    ),
                    passed=passed,
                    actual=intent_name,
                    detail=f"confidence={confidence:.2f}",
                )
            ]

            result = CaseResult(
                case_id=case.id,
                passed=passed,
                response="",
                intent=intent_name,
                confidence=confidence,
                assertion_results=assertion_results,
            )
            eval_results.append(result)

        failed = [
            r for r in eval_results if not r.passed and r.case_id.startswith("intent_")
        ]
        if failed:
            fail_details = "\n".join(
                f"  {r.case_id}: expected={r.assertion_results[0].assertion.value}, got={r.intent}"
                for r in failed
                if r.assertion_results
            )
            pytest.fail(f"Intent classification failures:\n{fail_details}")
