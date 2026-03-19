"""Daily conversation summarization — compresses old message history.

Stub implementation. Full implementation will:
1. Find conversations older than 48h not yet summarized
2. Summarize via LLM (cheap model, batch API)
3. Store in conversation_summaries table
4. Cache latest summary in Redis
"""

from src.telemetry.langfuse_integration import observe
from src.telemetry.logger import get_logger

_log = get_logger("jobs.summarize_conversations")


@observe("job.summarize_conversations")
async def run_summarize_conversations() -> dict:
    _log.info("summarize_conversations.stub")
    return {"summarized": 0, "status": "stub"}
