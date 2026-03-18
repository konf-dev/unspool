import statistics

import pytest

from tests.eval.client import EvalClient
from tests.eval.fixtures import InMemoryStore, eval_items, eval_messages
from tests.eval.loader import load_golden_cases
from tests.eval.types import CaseResult

pytestmark = pytest.mark.eval

_MAX_LATENCY_MS = 10_000
_REPS = 3


@pytest.mark.asyncio
class TestPerformance:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("performance_benchmarks.yaml", tag_filter=eval_tag)

    async def test_pipeline_latency(
        self,
        cases: list,
        eval_client: EvalClient,
        eval_results: list[CaseResult],
    ) -> None:
        for case in cases:
            latencies = []
            last_response = ""
            error_msg = None

            for _rep in range(_REPS):
                store = InMemoryStore(
                    initial_items=eval_items(),
                    initial_messages=eval_messages(),
                )
                try:
                    resp = await eval_client.send_message(case.message, store=store)
                    latencies.append(resp.latency_ms)
                    last_response = resp.response_text
                except Exception as e:
                    error_msg = str(e)
                    break

            if latencies:
                p50 = statistics.median(latencies)
                passed = p50 < _MAX_LATENCY_MS
            else:
                p50 = 0.0
                passed = False

            eval_results.append(
                CaseResult(
                    case_id=case.id,
                    passed=passed,
                    response=last_response,
                    latency_ms=p50,
                    error=error_msg,
                )
            )

        failed = [
            r for r in eval_results if not r.passed and r.case_id.startswith("perf_")
        ]
        if failed:
            details = [f"  {r.case_id}: P50={r.latency_ms:.0f}ms" for r in failed]
            pytest.fail("Performance failures:\n" + "\n".join(details))
