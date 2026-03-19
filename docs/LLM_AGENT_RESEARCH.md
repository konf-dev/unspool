# LLM Agent Research for Consumer Products (March 2026)

Research compiled March 2026. All claims are sourced from web searches; URLs provided for verification. Items marked **[UNCERTAIN]** could not be fully verified.

---

## 1. Available Reasoning/Tool-Calling LLMs

### OpenAI Models

#### GPT-4.1 Family (Released April 14, 2025)

| Model | Context Window | Input $/1M | Output $/1M | Cached Input $/1M | Max Output |
|---|---|---|---|---|---|
| gpt-4.1 | 1M tokens | $2.00 | $8.00 | $0.50 (75% off) | **[UNCERTAIN]** |
| gpt-4.1-mini | 1M tokens | $0.40 | $1.60 | $0.10 (75% off) | **[UNCERTAIN]** |
| gpt-4.1-nano | 1M tokens | $0.05 | $0.20 | $0.0125 (75% off) | **[UNCERTAIN]** |

- All three support **native tool/function calling** and are described as excelling at instruction following and tool calling.
- All three support **structured outputs** (strict mode with JSON Schema).
- All three support **streaming** with tool calls.
- **Prompt caching**: 75% discount on cached input (up from 50% for older models). Automatic, prefix-based, minimum 1,024 tokens. Cache granularity: 128-token increments.
- 26% cheaper than GPT-4o for median queries. GPT-4.1 mini matches or exceeds GPT-4o intelligence while reducing latency by ~50% and cost by ~83%.

Sources: [OpenAI GPT-4.1 announcement](https://openai.com/index/gpt-4-1/), [OpenAI Pricing](https://developers.openai.com/api/docs/pricing), [PromptHub Guide](https://www.prompthub.us/blog/the-complete-guide-to-gpt-4-1-models-performance-pricing-and-prompting-tips)

#### o-Series Reasoning Models

| Model | Context Window | Input $/1M | Output $/1M | Max Output |
|---|---|---|---|---|
| o3 (after 80% price cut, June 2025) | 200K tokens | $2.00 | $8.00 | 100K |
| o3-mini | 200K tokens | $1.10 | $4.40 | 100K |
| o4-mini (Released April 16, 2025) | 200K tokens | $1.10 | $4.40 | 100K |
| o3-pro | 200K tokens | $20.00 | $80.00 | 100K |

- o3 and o4-mini support **native tool calling within their chain of thought (CoT)**. Tools are invoked inside the reasoning process, not just as a post-hoc step.
- These models **preserve reasoning tokens across requests and tool calls** in the Responses API, improving intelligence and reducing cost.
- Tool limits: fewer than ~100 tools and ~20 arguments per tool is "in-distribution" and reliable.
- o3 also available in **flex mode**: $5 input / $20 output per 1M tokens (higher latency, lower cost).
- Unlike o1, o3/o4-mini fully support function calling, structured outputs, and Batch API.
- **Key quirk**: Do NOT use explicit chain-of-thought prompting with reasoning models -- they reason internally, and asking them to reason more can hurt performance.

Sources: [OpenAI o3/o4-mini announcement](https://openai.com/index/introducing-o3-and-o4-mini/), [o3/o4-mini Function Calling Guide](https://developers.openai.com/cookbook/examples/o-series/o3o4-mini_prompting_guide/), [VentureBeat on o3 price drop](https://venturebeat.com/ai/openai-announces-80-price-drop-for-o3-its-most-powerful-reasoning-model)

#### GPT-5.4 Family (Latest Flagship, ~Early 2026)

| Model | Input $/1M | Output $/1M | Cached Input $/1M |
|---|---|---|---|
| gpt-5.4 | $2.50 | $15.00 | $0.25 |
| gpt-5.4-mini | $0.75 | $4.50 | $0.075 |
| gpt-5.4-nano | $0.20 | $1.25 | $0.02 |

**[UNCERTAIN]**: These appeared on the OpenAI pricing page as "our latest models" as of March 2026. Context windows and detailed specs not confirmed in my searches. They appear to have replaced the GPT-4.1 series as the flagship.

Source: [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)

---

### Anthropic Claude Models

#### Current Models (March 2026)

| Model | Context Window | Input $/1M | Output $/1M | Max Output | Released |
|---|---|---|---|---|---|
| Claude Opus 4.6 | 1M tokens | $5.00 | $25.00 | 128K | Feb 5, 2026 |
| Claude Sonnet 4.6 | 1M tokens | $3.00 | $15.00 | 64K | Feb 17, 2026 |
| Claude Haiku 4.5 | 200K tokens | $1.00 | $5.00 | 64K | Oct 15, 2025 |

- All current models support **tool use** (native function calling).
- All support **extended thinking** (deep reasoning mode).
- Opus 4.6 and Sonnet 4.6 support **adaptive thinking**.
- All support **parallel tool calls** (enabled by default, can be disabled with `disable_parallel_tool_use=True`).
- All support **streaming** with tool use blocks.
- **Prompt caching pricing**: Cache write = 1.25x base input (5-min TTL) or 2x base input (1-hr TTL). Cache read = 0.1x base input (90% discount).
- Tool definitions count against context window and are billed as input tokens.
- No strict limit on number of tools, but quality degrades with too many. Namespacing recommended (e.g., `github_list_prs`, `slack_send_message`).

**`tool_choice` options**: `auto` (default), `any` (must use a tool), `tool` (force specific tool), `none` (prevent tool use). Note: `any` and `tool` are NOT supported when using extended thinking.

#### Legacy Models Still Available

| Model | Context Window | Input $/1M | Output $/1M | Max Output |
|---|---|---|---|---|
| Claude Sonnet 4.5 | 1M (with beta header) / 200K default | $3.00 | $15.00 | 64K |
| Claude Opus 4.5 | 200K | $5.00 | $25.00 | 64K |
| Claude Sonnet 4 | 1M (with beta header) / 200K default | $3.00 | $15.00 | 64K |
| Claude Opus 4 | 200K | $15.00 | $75.00 | 32K |

Sources: [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview), [Claude Pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Claude Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use)

---

### Google Gemini Models

| Model | Context Window | Input $/1M | Output $/1M | Released |
|---|---|---|---|---|
| Gemini 2.5 Pro | 1M tokens | $1.00 | $10.00 | June 17, 2025 |
| Gemini 2.5 Flash | 1M tokens | $0.30 | $2.50 | June 17, 2025 |

- Both support **tool calling / function calling**.
- Both support **structured outputs**.
- Gemini 2.5 Flash includes built-in "thinking" capabilities.
- Both can connect to external tools/APIs, return structured JSON, search the web, and write/execute code in a sandboxed environment.
- Google also released newer Gemini 3.x series models **[UNCERTAIN]**: Gemini 3.1 Pro, Gemini 3 Flash, Gemini 3.1 Flash-Lite appeared in documentation but pricing/specs not confirmed.

Sources: [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing), [Gemini Models](https://ai.google.dev/gemini-api/docs/models), [Gemini 2.5 Pro Pricing](https://pricepertoken.com/pricing-page/model/google-gemini-2.5-pro)

---

### Open-Source / Other Models

#### Meta Llama 4 (Released 2025)

| Model | Architecture | Active Params | Total Params | Context Length |
|---|---|---|---|---|
| Llama 4 Scout (17B-16E) | MoE, 16 experts | 17B | ~109B | **[UNCERTAIN]** |
| Llama 4 Maverick (17B-128E) | MoE, 128 experts | 17B | ~400B | 512K tokens |

- Supports **tool calling** with the `llama4_pythonic` tool parser.
- Parallel tool calls supported in Llama 4 (not in Llama 3).
- **Limitation**: Llama 4 Maverick's function calling is optimized for single-turn; multi-turn is "under development" and parallel function calling is not supported for Maverick.
- Apache 2.0 license, free for commercial use.

Source: [Llama API Tool Calling](https://llama.developer.meta.com/docs/features/tool-calling/), [GPT-trainer Llama 4](https://gpt-trainer.com/blog/llama+4+evolution+features+comparison)

#### Mistral Large 3

- 675B total parameters, 41B active per forward pass (sparse MoE).
- Apache 2.0 license.
- Function-calling capable models include: Mistral Large, Mistral Small, Codestral, Ministral 8B/3B, Pixtral 12B/Large, Mistral Nemo.
- Uses special tokens (`[TOOL_CALLS]`, `[TOOL_RESULTS]`) for function calling.

Source: [Mistral Function Calling Docs](https://docs.mistral.ai/capabilities/function_calling)

---

### Model Comparison Summary for Unspool

| Use Case | Best Options | Why |
|---|---|---|
| Primary chat (quality + cost) | gpt-4.1-mini, Claude Sonnet 4.6, Gemini 2.5 Flash | Good tool calling, reasonable cost |
| Fast classification | gpt-4.1-nano ($0.05/$0.20) | Cheapest, fastest, good tool calling |
| Complex reasoning | o3, o4-mini, Claude Opus 4.6 | Deep reasoning with tool calling |
| Budget with quality | Gemini 2.5 Flash ($0.30/$2.50) | Very cheap, 1M context |

---

## 2. Tool Calling Best Practices

### OpenAI Official Recommendations

**Defining Tools:**
- Always enable **strict mode** (`strict: true`) -- guarantees model output matches your JSON Schema exactly.
- Set `additionalProperties: false`, mark all fields as `required`, and use `null` type option for optional fields.
- Design **intuitive functions** -- use enums and object structure to make invalid states unrepresentable.
- Front-load critical rules in descriptions. Include usage criteria: when to use AND when NOT to use.

**Descriptions:**
- Use the system prompt to describe when (and when not) to use each function.
- 3-4+ sentences recommended per tool description.
- Include: what the tool does, when to use it, parameter meanings, caveats/limitations.

**Parallel vs Sequential:**
- Models can call multiple functions in one turn by default.
- Set `parallel_tool_calls: false` to ensure exactly zero or one tool call.
- **Important**: Structured Outputs is NOT compatible with parallel function calls. If you need strict schema validation, disable parallel calling.

**Tool Count:**
- o3/o4-mini: <100 tools and <20 arguments per tool is "in-distribution."
- Tool definitions count as input tokens. More tools = higher cost per call.
- Use tool search / deferred loading for large tool sets.

**o3/o4-mini Specific:**
- Flatten argument structures -- deeply nested parameters degrade reliability.
- Do NOT use explicit chain-of-thought prompting with reasoning models.
- Add explicit instructions: "Do NOT promise to call a function later. If a function call is required, emit it now."
- Discard irrelevant history and summarize context when conversations get long.

Sources: [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling), [o3/o4-mini Prompting Guide](https://developers.openai.com/cookbook/examples/o-series/o3o4-mini_prompting_guide/), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

### Anthropic Official Recommendations

**Tool Definition Structure:**
```json
{
  "name": "get_weather",
  "description": "Get the current weather in a given location. Use when the user asks about weather.",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": { "type": "string", "description": "City and state, e.g. San Francisco, CA" }
    },
    "required": ["location"]
  },
  "input_examples": [
    { "location": "San Francisco, CA", "unit": "fahrenheit" }
  ]
}
```

**Best Practices:**
- Consolidate related operations into fewer tools with action parameters rather than many separate tools. E.g., one `git_operation(action: "create"|"review"|"merge")` instead of three separate tools.
- Return only necessary information in tool results -- use semantic identifiers (slugs, UUIDs) not opaque internal references.
- Provide `input_examples` for complex tools (adds ~20-200 tokens).
- Use meaningful namespacing: `github_list_prs`, `slack_send_message`.
- **Tool Search Tool** (new): mark tools with `defer_loading: true` to make them discoverable on-demand. Claims 85% reduction in token usage while maintaining access to full tool library.

**Error Handling:**
- Return errors with `is_error: true` in tool result. Claude handles gracefully and can request clarification or retry.

Sources: [Claude Tool Use Implementation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use), [Anthropic Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use), [Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

---

## 3. Conversation Context Management

### Message Format with Tool Calls

**OpenAI (Responses API):**
- Uses "Items" (not Messages). An Item is a union of types: message, function_call, function_call_output, etc.
- The Responses API manages conversation state server-side. You reference a previous response ID to continue.
- The Chat Completions API requires you to maintain the full conversation array yourself, including tool_call and tool_result messages.
- OpenAI recommends the Responses API for new projects.

**Anthropic (Messages API):**
- Tool use: Claude returns `tool_use` content blocks with `stop_reason: "tool_use"`.
- Tool results: You send a `user` message with `tool_result` content blocks, referencing the `tool_use_id`.
- **Critical**: tool_result blocks must come FIRST in the content array, followed by any text.
- Multiple tool results from parallel calls go in a single user message.

Sources: [OpenAI Responses vs Chat Completions](https://simonwillison.net/2025/Mar/11/responses-vs-chat-completions/), [OpenAI Migration Guide](https://developers.openai.com/api/docs/guides/migrate-to-responses), [Claude Messages API](https://platform.claude.com/docs/en/build-with-claude/working-with-messages)

### Context Window Management Strategies

**Hierarchical Summarization:**
- Compress older conversation segments while preserving essential information.
- Recent exchanges remain verbatim; older content gets compressed into summaries.
- Multi-level: detailed summaries every 5 messages, moderate every 25, high-level every 100.

**Recursive Summarization:**
- Evicted messages are summarized along with existing summaries from previously summarized messages.
- Older messages have progressively less influence on the summary.

**Observation Masking:**
- Simpler alternative: keep only the M most recent observations. Omit older tool results entirely.
- Research shows this can perform equally or better than complex LLM summarization for code-centric agents.

**Context-Folding (FoldGRPO):**
- An agent branches into a sub-trajectory and folds it back, replacing intermediate steps with a concise summary.
- Claims 10x smaller active context window while matching or surpassing baselines.

**Git-Context-Controller (GCC):**
- Structures agent memory like a Git repository: COMMIT, BRANCH, MERGE, CONTEXT operations.
- State-of-the-art for software engineering and self-replication tasks.

Sources: [JetBrains Research: Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/), [mem0 Chat History Summarization](https://mem0.ai/blog/llm-chat-history-summarization-guide-2025), [GetMaxim Context Management](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)

### How Coding Agents Manage Context

**Claude Code:**
- Uses full 200K context (1M beta with Opus 4.6).
- Shows context usage in the prompt box.
- Auto-compacts when nearing limits, or manual `/compact` command.
- Every message, file inspection, and command accumulates in context.

**Cursor:**
- Normal mode: 128K, Max Mode: 200K.
- Uses RAG-like retrieval on the local filesystem for codebase context.
- May shorten input or drop older context to maintain speed.

**Key Insight:** All coding agents face the same fundamental problem -- session history accumulates and must be compacted/summarized, losing fidelity. The practical strategy is to compact early and often.

Sources: [Claude Code vs Cursor](https://www.qodo.ai/blog/claude-code-vs-cursor/), [Vibe Code Without Burning Context](https://ai.plainenglish.io/how-to-vibe-code-without-burning-your-context-window-a-cross-tool-setup-guide-for-claude-code-dadb7c524ab0)

---

## 4. Agent Architecture Patterns

### Anthropic's Framework (from "Building Effective Agents")

Anthropic draws a key distinction:
- **Workflows**: LLMs and tools orchestrated through **predefined code paths**.
- **Agents**: LLMs **dynamically direct their own processes** and tool usage.

**Start simple**: "Finding the simplest solution possible, and only increasing complexity when needed. This might mean not building agentic systems at all."

#### Workflow Patterns (Increasing Complexity)

1. **Prompt Chaining**: Sequential steps with programmatic checks between them. Use when tasks decompose cleanly into fixed subtasks.

2. **Routing**: Classify inputs and direct to specialized handlers. Use for distinct categories that need different treatment.

3. **Parallelization**: Run multiple LLM calls simultaneously. Two variants:
   - *Sectioning*: Independent subtasks in parallel.
   - *Voting*: Multiple attempts for confidence.

4. **Orchestrator-Workers**: Central LLM dynamically decomposes tasks and delegates. Use when subtasks can't be predicted in advance.

5. **Evaluator-Optimizer**: One LLM generates, another evaluates, iterating. Use when clear evaluation criteria exist.

#### Agent Pattern

- Autonomous systems where the LLM controls its own process.
- Operates in environment-feedback loops: tool results, code execution output.
- Use for open-ended problems where number of steps is unpredictable.
- **Caveat**: "Higher costs, and the potential for compounding errors. We recommend extensive testing in sandboxed environments."

Source: [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)

### ReAct Pattern (Reason + Act)

- **Loop**: Thought -> Action -> Observation -> Thought -> ...
- LLM generates reasoning traces AND task-specific actions in interleaved manner.
- Reduces hallucinations compared to chain-of-thought alone by grounding reasoning with real actions.
- Works well for interactive tasks where the model needs to fetch information between reasoning steps.

Source: [Prompt Engineering Guide: ReAct](https://www.promptingguide.ai/techniques/react), [IBM: What is a ReAct Agent](https://www.ibm.com/think/topics/react-agent)

### Plan-and-Execute Pattern

- LLM first creates a comprehensive multi-step plan.
- A separate executor carries out the plan step by step.
- Better for tasks where upfront planning is feasible and the plan rarely needs revision.
- Contrast with ReAct: ReAct is iterative and adaptive; Plan-and-Execute is deliberate and structured.

Source: [ReAct vs Plan-and-Execute Comparison](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)

### OpenAI Agents SDK

Core primitives:
- **Agent**: LLM equipped with instructions, tools, and behavior.
- **Handoffs**: Agent-to-agent delegation for specialized tasks.
- **Guardrails**: Validation of agent inputs and outputs.
- **Runner**: Manages execution -- receiving input, handling retries, choosing tools, streaming responses.

2026 production pattern: `Frontend -> FastAPI Backend -> Workflow Runner -> OpenAI Agent -> Persistent Session`

Available in both Python and TypeScript/JavaScript.

Sources: [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), [OpenAI Agents SDK Review](https://mem0.ai/blog/openai-agents-sdk-review)

### "LLM Picks Tools" vs "Code Routes to Tools"

This is the fundamental architectural decision:

| Approach | When to Use | Tradeoffs |
|---|---|---|
| LLM picks tools (agent) | Open-ended tasks, unpredictable workflows | More flexible, higher cost, risk of wrong tool selection |
| Code routes to tools (workflow) | Predictable task categories, clear intent mapping | More reliable, cheaper, less flexible |
| Hybrid (Unspool's current approach) | Known intents with LLM fallback | Best of both -- classify intent in code, let LLM handle ambiguous cases |

**For Unspool's case**: The current config-driven orchestrator (classify intent -> route to pipeline -> pipeline calls tools) is the workflow pattern. Adding a ReAct-style agent loop within a pipeline would enable dynamic tool selection for complex queries while keeping the routing layer deterministic.

---

## 5. Competitors: How AI Assistants Handle This

### ChatGPT (with tools)

- Built-in tools: web search (Bing), code interpreter (sandboxed Python), file search (vector stores/RAG), computer use.
- Decision-making relies on **metadata and descriptions** -- developers write "Use this when..." descriptions.
- Plugins describe themselves via documentation; ChatGPT selects based on user intent.
- Code interpreter runs in a persistent session for the duration of a chat conversation.
- File search provides hosted RAG with vector stores.
- o3/o4-mini can agentively use and combine every tool within ChatGPT in a single turn.

Sources: [OpenAI Plugins](https://openai.com/index/chatgpt-plugins/), [OpenAI DevDay 2025](https://developers.openai.com/blog/openai-for-developers-2025/)

### Motion AI (Auto-Scheduling)

- Scans calendar for open slots, respects existing meetings.
- Schedules tasks by deadline, priority, and chunking rules (e.g., 2-hour task in 30-minute blocks).
- ASAP overrides all other scheduling signals.
- **Dynamically reshuffles** entire schedule when you add a meeting or move a task -- "optimizes dozens of times a day."
- Analyzes: priorities, urgency, deadlines, dependencies, meeting schedules, availability, work preferences, productivity patterns.
- Pricing: ~$34/month (individual).

Source: [Motion AI Task Manager](https://www.usemotion.com/features/ai-task-manager), [Motion Auto-scheduling](https://www.usemotion.com/help/time-management/auto-scheduling)

### Goblin.tools (ADHD-Specific)

- Collection of small, single-task tools for neurodivergent users.
- **Magic To Do**: Breaks abstract tasks into micro-step checklists using AI.
- Key insight: attacks task paralysis by generating dopamine-triggering micro-steps.
- Free website (no ads, no sign-up). Mobile apps have small one-time fee.
- Very simple -- no scheduling, no calendar, no persistence.

Source: [Goblin Tools About](https://goblin.tools/About), [Goblin Tools Review](https://futureaiblog.com/goblin-tools-ai-for-neurodivergent-individuals/)

### Tiimo (ADHD Visual Planning)

- Highly visual, icon-based timeline.
- Shows how much visual space a task takes in your day.
- Countdown timers and visual routines.
- Prevents over-scheduling by making time visible.
- Not AI-first; more of a visual planning tool.

Source: [ADHD Task Management Apps](https://blog.saner.ai/best-adhd-task-management-apps/)

### Saner.AI (ADHD, newer)

- AI-first ADHD task management, gaining traction in 2026.
- **[UNCERTAIN]**: Could not find detailed architecture information.

### Notion AI (Agents)

- Launched Notion 3.0 with autonomous AI Agents (September 2025).
- Agents can execute multi-step workflows, analyze data across multiple pages/databases.
- Can sustain tasks for over 20 minutes with an advanced memory system.
- Uses multiple LLM backends: GPT-5, Claude Opus 4.1, o3.
- Block-based architecture: every content piece is a modular block.

Source: [Notion 3.0 Agents](https://www.notion.com/releases/2025-09-18)

### Granola AI (Meeting Notes)

- **Bot-free**: Captures audio from laptop microphone locally, never joins meetings as a bot.
- AI processes speech in real-time, extracts insights and action items.
- **Immediately discards audio** after processing -- privacy-first.
- Can operate in classified/confidential meetings where recording bots are banned.
- SOC 2 Type 2 compliant.
- Expanding from individual productivity to organizational memory infrastructure (2.0 upgrade, May 2025).

Source: [Granola AI Strategy](https://michaelgoitein.substack.com/p/granolas-revolutionary-ai-strategy), [Zapier: What is Granola](https://zapier.com/blog/granola-ai/)

---

## 6. Embedding Models

### OpenAI Embedding Models

| Model | Dimensions | Pricing ($/1M tokens) | Batch Pricing | Max Input |
|---|---|---|---|---|
| text-embedding-3-small | 1536 (configurable) | $0.02 | $0.01 | 8K tokens |
| text-embedding-3-large | 3072 (configurable) | $0.13 | $0.065 | 8K tokens |

- Both support **Matryoshka representation learning**: you can shorten embeddings (reduce dimensions) via the `dimensions` API parameter without losing concept-representing properties.
- text-embedding-3-small at reduced dimensions (e.g., 512) is often good enough for most use cases.
- No newer OpenAI embedding models found beyond text-embedding-3 series as of March 2026.

Source: [OpenAI text-embedding-3-small](https://platform.openai.com/docs/models/text-embedding-3-small), [OpenAI text-embedding-3-large](https://platform.openai.com/docs/models/text-embedding-3-large), [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)

### Voyage AI (Strong Alternative)

| Model | Dimensions | Pricing ($/1M tokens) | Max Input |
|---|---|---|---|
| voyage-3-large | 2048 (also 1024, 512, 256) | $0.18 | 32K tokens |

- Outperforms OpenAI text-embedding-3-large by 9.74% on average.
- With 512-dimensional binary embeddings, outperforms OpenAI-v3-large (3072 float) by 1.16% while requiring 200x less storage.
- Supports int8, uint8, binary, ubinary quantization.
- 32K token context (vs OpenAI's 8K) -- significant for longer documents.
- First 200M tokens free per account.
- Voyage AI also offers `voyage-context-3` for chunk-level details with global document context.

Source: [Voyage-3-large announcement](https://blog.voyageai.com/2025/01/07/voyage-3-large/), [Voyage AI Docs](https://docs.voyageai.com/docs/embeddings)

### Cohere Embed 4 (Multimodal, January 2026)

- $0.12/MTok for text, $0.47/MTok for images.
- Multilingual, multimodal (text + images).
- Converts text and images into semantic search vectors.

Source: [Embedding Models Comparison 2026](https://reintech.io/blog/embedding-models-comparison-2026-openai-cohere-voyage-bge)

### Mistral Codestral Embed (May 2025)

- $0.15/MTok, code-specialized retrieval.

Source: [Embedding Models Comparison](https://reintech.io/blog/embedding-models-comparison-2026-openai-cohere-voyage-bge)

### Recommendation for Unspool

Unspool currently uses OpenAI text-embedding-3 with 1536 dimensions (pgvector). This remains a solid choice. If retrieval quality becomes an issue, voyage-3-large is the strongest alternative, particularly given its 32K context length for embedding longer brain dumps.

---

## 7. Cost Optimization

### Prompt Caching

**OpenAI:**
- Automatic, no API flag needed.
- Matches leading prefixes only -- **stable content must come before dynamic content**.
- Minimum 1,024 tokens, granularity in 128-token increments.
- GPT-4.1 series: 75% discount on cached input (was 50% for older models).
- Cache lasts 5-10 minutes of inactivity (up to 1 hour). Extended retention up to 24 hours available for GPT-5.1 and GPT-4.1.
- **Practical savings**: 50% cache rate = 33% cost savings; 70% cache rate = 55% savings.

**Anthropic:**
- Explicit: you mark portions with cache control breakpoints.
- 5-minute TTL: write = 1.25x base input, read = 0.1x base input.
- 1-hour TTL: write = 2x base input, read = 0.1x base input.
- Cache pays off after just one read for 5-minute TTL (1.25x write then 0.1x reads).
- Latency reduction: up to 85% for long prompts. Example: 100K-token book from 11.5s to 2.4s.
- Cache refreshes on each use within TTL window.
- Starting Feb 5, 2026: workspace-level cache isolation (was organization-level).

**Google:**
- Gemini also supports prompt caching, priced similarly to Anthropic's approach.

Sources: [OpenAI Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching), [OpenAI Prompt Caching 201](https://developers.openai.com/cookbook/examples/prompt_caching_201), [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

### Batch API

- OpenAI Batch API: **50% discount** on both input and output tokens.
- Upload JSONL file, results within 24 hours (typically 1-2 hours for small/medium batches).
- Supports chat completions, embeddings, and completions.
- Ideal for: embeddings generation, classification, extraction -- anything not time-sensitive.
- **For Unspool**: Batch API is perfect for post-conversation embedding generation (already done in background job).

Source: [OpenAI Batch API](https://community.openai.com/t/batch-api-is-now-available/718416)

### Token Minimization Strategies

1. **Cache system prompts and tool definitions** -- these are the same every call.
2. **Summarize old conversation turns** instead of including full history.
3. **Use smaller models for classification** -- gpt-4.1-nano at $0.05/$0.20 is ideal for intent classification.
4. **Return minimal tool results** -- only include fields the LLM needs for next step.
5. **Discard irrelevant history** -- remove old tool calls when they're no longer relevant.
6. **Use Batch API** for background processing (embeddings, pattern detection).
7. **Dynamic tool loading** -- only load tools relevant to the current intent.

### Cost Comparison for Unspool (Per User Message)

Assuming ~2 LLM calls per message: 1 classification (~500 tokens in/out) + 1 response (~2000 tokens in, ~500 out):

| Model | Classification Cost | Response Cost | Total per Message |
|---|---|---|---|
| gpt-4.1-nano + gpt-4.1-mini | ~$0.00004 | ~$0.0016 | ~$0.0016 |
| gpt-4.1-nano + gpt-4.1 | ~$0.00004 | ~$0.008 | ~$0.008 |
| Claude Haiku 4.5 + Sonnet 4.6 | ~$0.003 | ~$0.014 | ~$0.017 |
| Gemini 2.5 Flash (both) | ~$0.0015 | ~$0.005 | ~$0.007 |

**Note**: These are rough estimates. Actual costs depend on context size, tool definitions, and caching.

---

## 8. Streaming with Tool Calls

### OpenAI

- **Yes, streaming with tool calls is supported.** Set `stream: true` and get chunks with delta objects.
- When the model calls a tool during streaming, you receive the tool call as streamed chunks (function name, then arguments in pieces).
- The model may call multiple tools in a single streamed response (parallel tool calls).
- Set `parallel_tool_calls: false` to ensure exactly zero or one tool call per response.
- **Responses API** uses SSE events organized by purpose -- each event type signals a different lifecycle stage.

### Anthropic

- **Yes, streaming tool use blocks is supported.**
- **Fine-grained tool streaming** (beta, `fine-grained-tool-streaming-2025-05-14`): Streams tool parameters without buffering.
- **Caveat**: Because fine-grained streaming sends parameters without JSON validation, there is NO guarantee the resulting stream will complete with valid JSON. If `max_tokens` is hit, the stream may end mid-parameter.
- Tool use and extended thinking blocks **cannot be partially recovered** -- ensure complete handling.
- For invalid JSON from interrupted streams, wrap in `{ "INVALID_JSON": "<your invalid json string>" }` when sending back to the model.

### UX Patterns for "Thinking" While Tools Execute

1. **Show "thinking" indicator**: Display a pulsing indicator while the LLM processes.
2. **Stream text before/after tool calls**: The LLM often generates text like "I'll check that for you" before a tool call. Stream this to the user immediately.
3. **Show tool execution status**: "Looking up your tasks..." while the tool runs.
4. **Resume streaming after tool result**: Once the tool returns, the LLM continues generating (and streaming) the final response.
5. **For Unspool**: The current SSE streaming approach works well. Stream the "I'll look into that" text, show a brief indicator during tool execution, then stream the response.

Sources: [OpenAI Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses), [OpenAI Streaming Events Reference](https://platform.openai.com/docs/api-reference/responses-streaming), [Claude Fine-grained Tool Streaming](https://docs.claude.com/en/docs/agents-and-tools/tool-use/fine-grained-tool-streaming), [Claude Streaming Messages](https://docs.anthropic.com/en/api/messages-streaming)

---

## 9. Safety and Guardrails

### Prompt Injection Prevention

**The hard truth**: OpenAI states that "Prompt injection, much like scams and social engineering on the web, is unlikely to ever be fully 'solved.'" It is a "long-term AI security challenge" requiring continuous defense.

**Multi-Layered Defense (Defense in Depth):**

1. **Input Validation**: Extract only specific structured fields from external inputs. Use enums, validated JSON. Never let untrusted data directly drive agent behavior.

2. **Tool Permission Scoping**: AI agents should access production data through API layers with permission scoping, not direct database connections. Enforce access controls, audit logging, and rate limiting.

3. **Sandboxing**: When AI uses tools to run code or other programs, sandbox the execution environment. Prevents harmful changes from prompt injection.

4. **Instruction Hierarchy**: Train/prompt models to distinguish between trusted instructions (system prompt) and untrusted content (user input, tool results from external sources).

5. **Human-in-the-Loop**: Pause and ask for confirmation before sensitive actions (purchases, deletions, data access). ChatGPT implements this with "Watch Mode" for sensitive sites.

6. **Tool Confirmations**: Always enable tool approvals so users can review and confirm operations.

7. **Plan-Verify-Execute (PVE)**: LLM creates a plan upfront; actions are verified against the original plan before execution. Prevents tool results from modifying the agent's course of action.

Sources: [OpenAI Agent Safety](https://platform.openai.com/docs/guides/agent-builder-safety), [OpenAI Prompt Injections](https://openai.com/index/prompt-injections/), [OpenAI Designing Agents to Resist Prompt Injection](https://openai.com/index/designing-agents-to-resist-prompt-injection/), [CSA Guardrails Guide](https://cloudsecurityalliance.org/blog/2025/12/10/how-to-build-ai-prompt-guardrails-an-in-depth-guide-for-securing-enterprise-genai)

### Rate Limiting Tool Calls

- Apply per-user quotas and global caps.
- Budget protections: configure max tool calls per conversation turn, per session, per day.
- Monitor for unusual patterns (rapid tool calling, attempts to access unauthorized resources).

### For Unspool Specifically

Since Unspool's tools operate on the user's own data (items, messages) and the user is authenticated:
- **Lower risk**: No cross-user data access possible (RLS enforced).
- **Main risk**: User prompt-injecting to bypass the system's intent classification or make the AI behave differently than intended.
- **Mitigation**: Keep tool definitions in the system prompt (trusted), validate all tool inputs, log all tool calls with trace_id.

### Guardrails Frameworks

- **NeMo Guardrails** (NVIDIA, Apache 2.0): Dialog management and safety rails.
- **Guardrails AI**: Pre-built validators for output validation.
- **NIST AI RMF and ISO 42001**: Compliance frameworks now mandate specific controls for prompt injection prevention.

---

## Key Recommendations for Unspool

### Model Selection
1. **Classification**: gpt-4.1-nano ($0.05/$0.20) -- cheapest, fastest, good at instruction following.
2. **Response generation**: gpt-4.1-mini ($0.40/$1.60) for most messages, upgrade to gpt-4.1 for complex queries.
3. **Alternative**: Gemini 2.5 Flash ($0.30/$2.50) is compelling for cost -- 1M context, good tool calling.
4. **Keep Claude as fallback**: Claude Sonnet 4.6 has best personality/tone for chat applications.

### Architecture
1. **Keep the current workflow pattern** (intent classification -> pipeline routing). It's the right architecture per Anthropic's own recommendations.
2. **Add a tool-calling loop** within pipelines for complex queries that need dynamic tool selection.
3. **Use prompt caching aggressively** -- system prompt + tool definitions + user profile are stable across calls.
4. **Use Batch API** for all background processing (embeddings, pattern detection, decay jobs).

### Context Management
1. **Summarize old conversations** rather than including full history.
2. **Keep tool results minimal** -- only return what the LLM needs.
3. **Consider observation masking** for tool-heavy conversations -- drop old tool results entirely after they've been incorporated into the response.

### Streaming
1. **Current SSE approach is correct**. Stream text tokens to user, show indicator during tool execution, resume streaming after.
2. **Be careful with Anthropic's fine-grained tool streaming** -- JSON validity not guaranteed.

---

## Sources Index

### OpenAI
- [GPT-4.1 Announcement](https://openai.com/index/gpt-4-1/)
- [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
- [o3/o4-mini Announcement](https://openai.com/index/introducing-o3-and-o4-mini/)
- [o3/o4-mini Function Calling Guide](https://developers.openai.com/cookbook/examples/o-series/o3o4-mini_prompting_guide/)
- [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Agent Safety](https://platform.openai.com/docs/guides/agent-builder-safety)
- [Prompt Injections](https://openai.com/index/prompt-injections/)
- [Designing Agents to Resist Prompt Injection](https://openai.com/index/designing-agents-to-resist-prompt-injection/)
- [Responses API Migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Agents SDK](https://openai.github.io/openai-agents-python/)
- [OpenAI for Developers 2025](https://developers.openai.com/blog/openai-for-developers-2025/)
- [Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)

### Anthropic
- [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Claude Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Tool Use Implementation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use)
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Fine-grained Tool Streaming](https://docs.claude.com/en/docs/agents-and-tools/tool-use/fine-grained-tool-streaming)
- [Streaming Messages](https://docs.anthropic.com/en/api/messages-streaming)

### Google
- [Gemini Models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini Pricing](https://ai.google.dev/gemini-api/docs/pricing)

### Other Models
- [Mistral Function Calling](https://docs.mistral.ai/capabilities/function_calling)
- [Llama API Tool Calling](https://llama.developer.meta.com/docs/features/tool-calling/)
- [Voyage-3-large](https://blog.voyageai.com/2025/01/07/voyage-3-large/)
- [Voyage AI Docs](https://docs.voyageai.com/docs/embeddings)

### Architecture & Patterns
- [ReAct Prompting Guide](https://www.promptingguide.ai/techniques/react)
- [IBM: ReAct Agent](https://www.ibm.com/think/topics/react-agent)
- [ReAct vs Plan-and-Execute](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)
- [JetBrains: Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [mem0: Chat History Summarization](https://mem0.ai/blog/llm-chat-history-summarization-guide-2025)

### Competitors
- [Motion AI](https://www.usemotion.com/features/ai-task-manager)
- [Goblin Tools](https://goblin.tools/About)
- [Granola AI](https://michaelgoitein.substack.com/p/granolas-revolutionary-ai-strategy)
- [Notion 3.0 Agents](https://www.notion.com/releases/2025-09-18)

### Safety
- [CSA Guardrails Guide](https://cloudsecurityalliance.org/blog/2025/12/10/how-to-build-ai-prompt-guardrails-an-in-depth-guide-for-securing-enterprise-genai)
- [OpenAI Safety Best Practices](https://platform.openai.com/docs/guides/safety-best-practices)
