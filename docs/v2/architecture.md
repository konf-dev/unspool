# Architecture

## Core Principle: Event Stream as Single Source of Truth

The `event_stream` table is the **only write target**. It is an append-only, immutable log of everything that happens. All other data stores are downstream projections:

```
User Message
    │
    ▼
event_stream (append MessageReceived)
    │
    ├──► graph_nodes / graph_edges  (projection, built by cold path + hot path mutations)
    ├──► vw_messages                (view filtering MessageReceived / AgentReplied)
    ├──► vw_actionable              (view joining nodes with OPEN status + deadlines)
    ├──► vw_timeline                (view of nodes with HAS_DEADLINE edges)
    └──► vw_metrics                 (view of TRACKS_METRIC aggregation)
```

All writes flow through `append_event()`. The hot path's `mutate_graph` tool appends mutation events (`StatusUpdated`, `EdgeAdded`, `EdgeRemoved`, `ContentUpdated`, `NodeArchived`) then applies them to the graph tables. The cold path appends `NodeCreated`/`EdgeAdded` events. Chat endpoints append `MessageReceived`/`AgentReplied`.

## Dual-Path Agent Architecture

```
                    ┌──────────────────────────────────────┐
                    │           POST /api/chat             │
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────┐
                    │        Auth + Rate Limit              │
                    │    (Supabase JWT + Redis gate)        │
                    └──────────┬───────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Save user   │  │  Assemble    │  │  Update      │
    │ message     │  │  Context     │  │  last_inter  │
    │ event       │  │  (parallel)  │  │  action_at   │
    └─────────────┘  └──────┬───────┘  └──────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
         Profile      Graph Search    Deadlines
         (DB)         (pgvector)      (vw_actionable)
              │             │             │
              └─────────────┼─────────────┘
                            │
                    ┌───────▼──────────────────────────────┐
                    │          HOT PATH (foreground)        │
                    │  LangGraph: agent ↔ tools loop       │
                    │  - GPT-4.1, temperature 0.7          │
                    │  - Tools: query_graph, mutate_graph   │
                    │  - Max 5 iterations                   │
                    │  - SSE streaming to client            │
                    └───────┬──────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │                           │
              ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐
    │ Save assistant  │         │ Dispatch cold   │
    │ message event   │         │ path via QStash │
    └─────────────────┘         └────────┬────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  COLD PATH      │
                                │  (background)   │
                                │  - GPT-4.1-mini │
                                │  - Structured   │
                                │    Outputs      │
                                │  - Idempotent   │
                                │  - Semantic     │
                                │    dedup        │
                                └─────────────────┘
```

### Hot Path (Foreground, Real-Time)

The hot path handles the conversational experience. It:
1. Assembles context in parallel (profile, recent messages, graph search, deadlines)
2. Builds a dynamic system prompt from `agent_system.md` template
3. Runs a LangGraph state machine with 2 tools: `query_graph` and `mutate_graph`
4. Streams responses via SSE
5. Strips `<thought>` blocks from output before sending to client

**Key design: No `user_id` in tool params.** The LLM never sees or passes user_id. It's injected from LangGraph state in `call_tools()`, eliminating a hallucination vector.

### Cold Path (Background, Async)

The cold path extracts structured knowledge from user messages:
1. Dispatched via QStash (not `asyncio.create_task`) — retries on failure
2. Uses idempotency keys (SHA256 of user_id + message) to prevent duplicates
3. GPT-4.1-mini with Structured Outputs extracts nodes and edges
4. Semantic dedup: before creating a node, searches for >0.9 cosine similarity match
5. All writes go through `append_event()` → graph projection

### Nightly Synthesis

Runs at 3 AM UTC for all active users:
1. **Archive:** DONE items older than 7 days → `archived_action`
2. **Merge:** Nodes with >0.9 cosine similarity → remap edges, delete duplicate
3. **Decay:** Edge weights multiplied by 0.99 per night (min 0.01)

## Directory Structure

```
backend/
  config/           6 YAML config files
  prompts/          9 Jinja2 prompt templates
  src/
    main.py         FastAPI app, lifespan, routes, middleware
    auth/           3 auth strategies (Supabase JWT, QStash, Admin)
    core/           settings, database, models (10 ORM), graph ops, config loader, prompt renderer
    db/             redis (cache + rate limit), queries (all non-graph DB ops)
    agents/
      hot_path/     LangGraph workflow, tools, context assembly, system prompt
      cold_path/    extractor (idempotent), schemas, synthesis (nightly)
    api/            8 routers: chat, messages, subscribe, account, feed, webhooks, admin, gate
    integrations/   qstash, stripe, push
    jobs/           router + 5 job implementations
    proactive/      evaluator registry, engine, scheduled actions
    telemetry/      structlog, trace middleware, error reporting, langfuse, PII scrubbing
  supabase/migrations/  6 SQL migrations
  tests/            7 test modules + conftest
```
