import pytest

from tests.eval.client import EvalClient
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
        eval_client: EvalClient,
        eval_results: list[CaseResult],
    ) -> None:
        for case in cases:
            if eval_client.target == "local":
                intent_name, confidence = await self._classify_local(case.message)
            else:
                intent_name, confidence = await self._classify_remote(
                    case.message, eval_client
                )

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

    @staticmethod
    async def _classify_local(message: str) -> tuple[str, float]:
        from src.orchestrator.intent import classify_intent
        from src.orchestrator.types import Context

        ctx = Context(
            user_id="eval-user-001",
            trace_id="eval-trace",
            user_message=message,
        )
        intent_name, _pipeline, confidence = await classify_intent(message, ctx)
        return intent_name, confidence

    @staticmethod
    async def _classify_remote(message: str, client: EvalClient) -> tuple[str, float]:
        """Send message through the production API and infer intent from the
        pipeline that ran (visible in llm_usage via admin API)."""
        import httpx

        await client.cleanup_remote()
        resp = await client.send_message(message)

        if not client.admin_key:
            return resp.intent or "unknown", resp.confidence or 0.0

        # Look up what pipeline ran for this trace via admin API
        if resp.trace_id:
            async with httpx.AsyncClient(base_url=client.base_url) as http:
                usage_resp = await http.get(
                    f"/admin/trace/{resp.trace_id}",
                    headers={"X-Admin-Key": client.admin_key},
                    timeout=10.0,
                )
                if usage_resp.status_code == 200:
                    data = usage_resp.json()
                    usages = data.get("llm_usage", [])
                    if usages:
                        pipeline = usages[0].get("pipeline", "unknown")
                        return pipeline, 1.0

        return "unknown", 0.0
