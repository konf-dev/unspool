# Gemini Migration Plan

Switching from OpenAI (gpt-4.1 / text-embedding-3-small) to Google Gemini (gemini-2.5-flash / gemini-embedding-001) to reduce LLM costs ~90% on input tokens.

## Summary of Changes

- **Dependencies**: `langchain-openai` + `openai` → `langchain-google-genai` + `google-genai`
- **Hot path**: `ChatOpenAI` → `ChatGoogleGenerativeAI` (LangChain abstraction, tool binding works the same)
- **Cold path**: OpenAI structured outputs → Gemini `generate_content()` with `response_json_schema`
- **Proactive + patterns**: OpenAI `chat.completions.create()` → Gemini `generate_content_async()`
- **Embeddings**: `text-embedding-3-small` (1536d) → `gemini-embedding-001` (768d, L2-normalized)
- **DB migration**: `vector(1536)` → `vector(768)`, wipe pre-launch embeddings
- **Settings**: Per-pipeline provider/model config (`CHAT_PROVIDER`, `EXTRACTION_PROVIDER`, etc.)

## Gemini SDK Best Practices Applied

Following https://ai.google.dev/gemini-api/docs:

### Structured Output (cold path extraction)
- Uses `system_instruction` field to separate instructions from user content
- Uses `response_mime_type="application/json"` + `response_json_schema=Model.model_json_schema()`
- Uses snake_case config field names (Python SDK convention, not REST camelCase)
- See: https://ai.google.dev/gemini-api/docs/structured-output

### Embeddings
- L2-normalized at 768 dimensions (required for < 3072 dims per Gemini docs)
- Task-type optimized per use case:
  - `RETRIEVAL_DOCUMENT` for storing/indexing nodes (cold path)
  - `RETRIEVAL_QUERY` for searching nodes (hot path, context assembly)
  - `SEMANTIC_SIMILARITY` for dedup matching
- Batch embedding: multiple texts in single API call for cold path node creation
- See: https://ai.google.dev/gemini-api/docs/embeddings

### Thinking Budget
- Extraction (cold path): 8192 tokens — high reasoning for accurate graph extraction
- Chat (hot path): 4096 tokens — balanced reasoning for tool selection + responses
- Background (proactive/patterns): 0 tokens — disabled, simple generation tasks
- See: https://ai.google.dev/gemini-api/docs/thinking

### Temperature
- Extraction: 0 — deterministic, precise structured output
- Chat: 0.7 — natural, varied conversation
- Proactive: 0.8 — slightly creative for natural-sounding messages
- Patterns: 0 — reliable JSON analysis

### Thought Signatures
- LangChain `ChatGoogleGenerativeAI` handles thought signatures automatically
  across multi-turn agent loops (model → tool call → tool result → model)
- For Gemini 2.5, signatures are optional but improve reasoning continuity
- For Gemini 3 (future), signatures become mandatory during function calling
- See: https://ai.google.dev/gemini-api/docs/thought-signatures

## Per-Pipeline Configuration

Each pipeline declares its provider and model explicitly in `.env`:

```
CHAT_PROVIDER=gemini          # Hot path conversation
CHAT_MODEL=gemini-2.5-flash

EXTRACTION_PROVIDER=gemini    # Cold path graph extraction
EXTRACTION_MODEL=gemini-2.5-flash

BACKGROUND_PROVIDER=gemini    # Proactive messages + pattern detection
BACKGROUND_MODEL=gemini-2.5-flash

EMBEDDING_PROVIDER=gemini     # Vector embeddings
EMBEDDING_MODEL=gemini-embedding-001

GOOGLE_API_KEY=AIza...        # One key per provider
```

To switch any single pipeline to a different provider, change that pipeline's
`*_PROVIDER` and `*_MODEL`, and ensure the corresponding `*_API_KEY` is set.

## Verification

1. `pip install -r backend/requirements.txt`
2. `python -c "from src.integrations.gemini import get_embedding; import asyncio; asyncio.run(get_embedding('test'))"`
3. `python eval/smoke_test.py`
4. Check Langfuse traces
5. Cold path extraction test
6. Embedding dimension: `SELECT embedding FROM graph_nodes LIMIT 1` — verify 768-dim, norm ≈ 1.0
