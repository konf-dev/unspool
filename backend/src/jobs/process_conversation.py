import re

from src.db.supabase import (
    get_items_without_embeddings,
    get_messages,
    save_entity,
    save_item_event,
    save_memory,
    update_item_embedding,
)
from src.llm.embedding import OpenAIEmbedding
from src.llm.registry import get_llm_provider
from src.orchestrator.prompt_renderer import render_prompt
from src.telemetry.logger import get_logger

_log = get_logger("jobs.process_conversation")

_NAME_PATTERN = re.compile(
    r"\b(?:call|email|text|tell|ask|meet with|meeting with|talk to)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b"
)
_PLACE_PATTERN = re.compile(
    r"\b(?:at|in|to|from|near)\s+(?:the\s)?([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\b"
)


async def run_process_conversation(user_id: str, message_ids: list[str]) -> dict:
    _log.info(
        "process_conversation.start",
        user_id=user_id,
        message_count=len(message_ids),
    )

    messages = await get_messages(user_id, limit=len(message_ids))
    relevant = [m for m in messages if str(m["id"]) in message_ids]

    embedder = OpenAIEmbedding()
    items = await get_items_without_embeddings(user_id)
    embedded_count = 0
    for item in items:
        text = f"{item['interpreted_action']} {item['raw_text']}"
        embedding = await embedder.embed(text)
        await update_item_embedding(str(item["id"]), embedding)
        await save_item_event(
            item_id=str(item["id"]),
            user_id=user_id,
            event_type="created",
        )
        embedded_count += 1

    entity_count = 0
    for msg in relevant:
        if msg["role"] != "user":
            continue
        content = msg["content"]

        for match in _NAME_PATTERN.finditer(content):
            name = match.group(1)
            await save_entity(user_id, name, "person", content[:200])
            entity_count += 1

        for match in _PLACE_PATTERN.finditer(content):
            place = match.group(1)
            await save_entity(user_id, place, "place", content[:200])
            entity_count += 1

    user_texts = [m["content"] for m in relevant if m["role"] == "user"]
    memory_count = 0
    if user_texts:
        try:
            rendered = render_prompt("extract_memories.md", {"user_messages": user_texts[-5:]})
            provider = get_llm_provider()
            result = await provider.generate(
                messages=[
                    {"role": "system", "content": rendered},
                    {"role": "user", "content": "Extract facts from the messages above."},
                ],
            )
            facts_text = result.content
            if facts_text.strip().upper() != "NONE":
                for line in facts_text.strip().split("\n"):
                    line = line.strip().lstrip("- ")
                    if line and len(line) > 5:
                        source_id = str(relevant[0]["id"]) if relevant else None
                        await save_memory(
                            user_id=user_id,
                            type="semantic",
                            content=line,
                            source_message_id=source_id,
                        )
                        memory_count += 1
        except (ConnectionError, TimeoutError, ValueError) as exc:
            _log.warning(
                "process_conversation.memory_extraction_failed",
                error=str(exc),
                exc_info=True,
            )

    _log.info(
        "process_conversation.done",
        embedded=embedded_count,
        entities=entity_count,
        memories=memory_count,
    )
    return {
        "embedded": embedded_count,
        "entities": entity_count,
        "memories": memory_count,
    }
