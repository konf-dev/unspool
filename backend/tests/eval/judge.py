import json
import os

from tests.eval.types import JudgeCriterion, JudgeResult

_SYSTEM_PROMPT = """\
You are an evaluator for Unspool, an AI personal assistant for people with ADHD.

Core design principles you must judge against:
- ONE THING AT A TIME: When asked "what should I do?", the AI must suggest exactly ONE item, never a list.
- NO UNSOLICITED EMPATHY: Don't assume the user is stressed or overwhelmed unless they explicitly say so. "I have an exam Friday" is matter-of-fact, not stressful.
- WARM CASUAL TONE: Lowercase, brief, conversational. Not corporate, not overly enthusiastic.
- BREVITY: Responses should be short — typically 1-3 sentences. No paragraphs.
- ACKNOWLEDGE BEFORE SOLVING: If the user expresses HIGH emotion, provide pure support first. If LOW/MEDIUM, briefly validate then proceed.
- NO LISTS: Never return bulleted lists, numbered lists, or multiple suggestions. One thing.
- NO ASSUMPTIONS: Don't project emotions, urgency, or importance the user didn't express.

Score the response on a scale of 1-10 for the specific criterion. Return ONLY valid JSON:
{"score": <float>, "reasoning": "<one sentence>"}
"""


async def judge_response(
    criterion: JudgeCriterion,
    user_message: str,
    ai_response: str,
) -> JudgeResult:
    model = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4o")
    provider = os.environ.get("EVAL_JUDGE_PROVIDER", "openai")

    prompt = (
        f"Criterion: {criterion.name}\n"
        f"Evaluation instruction: {criterion.prompt}\n\n"
        f"User message: {user_message}\n"
        f"AI response: {ai_response}\n\n"
        f"Score this response 1-10 on the criterion above."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        if provider == "openai":
            result = await _call_openai(messages, model)
        else:
            result = await _call_anthropic(messages, model)
    except Exception as e:
        return JudgeResult(
            criterion=criterion.name,
            score=0.0,
            reasoning=f"Judge API call failed: {e!s}",
            passed=False,
        )

    try:
        parsed = json.loads(result)
        score = float(parsed["score"])
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, KeyError, ValueError):
        score = 0.0
        reasoning = f"Failed to parse judge response: {result[:200]}"

    return JudgeResult(
        criterion=criterion.name,
        score=score,
        reasoning=reasoning,
        passed=score >= criterion.pass_threshold,
    )


async def _call_openai(messages: list[dict], model: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.1,
        max_tokens=200,
    )
    return response.choices[0].message.content or ""


async def _call_anthropic(messages: list[dict], model: str) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    system = messages[0]["content"] if messages[0]["role"] == "system" else ""
    user_messages = [m for m in messages if m["role"] != "system"]
    response = await client.messages.create(
        model=model,
        system=system,
        messages=user_messages,  # type: ignore[arg-type]
        temperature=0.1,
        max_tokens=200,
    )
    return response.content[0].text
