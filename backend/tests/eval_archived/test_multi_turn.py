import pytest

from tests.eval.client import EvalClient
from tests.eval.fixtures import InMemoryStore
from tests.eval.judge import judge_response
from tests.eval.loader import load_golden_cases
from tests.eval.types import CaseResult

pytestmark = pytest.mark.eval


@pytest.mark.asyncio
class TestMultiTurn:
    @pytest.fixture(scope="class")
    def cases(self, eval_tag: str | None) -> list:
        return load_golden_cases("multi_turn_flows.yaml", tag_filter=eval_tag)

    async def test_multi_turn_flows(
        self,
        cases: list,
        eval_client: EvalClient,
        eval_results: list[CaseResult],
    ) -> None:
        for case in cases:
            store = InMemoryStore()
            all_passed = True
            error_msg = None
            last_response = ""
            total_latency = 0.0

            try:
                # Each setup_message is a turn in the conversation
                all_messages = [
                    *[m["content"] for m in case.setup_messages if m["role"] == "user"],
                    case.message,
                ]

                for msg in all_messages:
                    resp = await eval_client.send_message(msg, store=store)
                    last_response = resp.response_text
                    total_latency += resp.latency_ms

                    # Add assistant response to store so next turn has context
                    await store.save_message(
                        user_id="eval-user-001",
                        role="assistant",
                        content=resp.response_text,
                    )

            except Exception as e:
                all_passed = False
                error_msg = str(e)

            # Judge the final response
            judge_results = []
            if not error_msg:
                for criterion in case.judge_criteria:
                    jr = await judge_response(criterion, case.message, last_response)
                    judge_results.append(jr)
                    if not jr.passed:
                        all_passed = False

            eval_results.append(
                CaseResult(
                    case_id=case.id,
                    passed=all_passed,
                    response=last_response,
                    latency_ms=total_latency,
                    judge_results=judge_results,
                    error=error_msg,
                )
            )

        failed = [
            r for r in eval_results if not r.passed and r.case_id.startswith("multi_")
        ]
        if failed:
            details = []
            for r in failed:
                if r.error:
                    details.append(f"  {r.case_id}: ERROR {r.error}")
                else:
                    j_fails = [jr for jr in r.judge_results if not jr.passed]
                    details.append(
                        f"  {r.case_id}: {[(j.criterion, j.score) for j in j_fails]}"
                    )
            pytest.fail("Multi-turn failures:\n" + "\n".join(details))
