# Graph Memory System

Production integration of the Postgres-native graph memory system into Unspool's pipeline. The graph provides a structured memory layer where user thoughts become nodes connected by bi-temporal edges, enabling context-aware retrieval that understands relationships, deadlines, and status.

## Architecture

```
User message → Pipeline → [graph_context loader] → LLM response
                                    ↓
                          build_active_subgraph()
                          ├── trigger: semantic (pgvector)
                          ├── trigger: temporal (date nodes)
                          ├── trigger: open_items (status edges)
                          ├── trigger: recent (activation time)
                          ├── trigger: suppression (surfaced edges)
                          └── trigger: graph_walk (neighbor cache)
                                    ↓
                          serialize_subgraph()
                          → <context>...</context> block

User message → Pipeline → [post_processing] → QStash → /jobs/process-graph
                                                              ↓
                                                   quick_ingest() → nodes + edges
                                                   embed_nodes() → halfvec embeddings
                                                   detect_feedback() → surfaced/done edges
```

The graph does NOT replace any existing system. It's an additional optional context source alongside `open_items`, `memories`, `recent_messages`, etc.

## Module Structure

```
backend/src/graph/
├── __init__.py
├── types.py          # Pydantic models: Node, Edge, ActiveSubgraph, IngestOutput, etc.
├── db.py             # All SQL operations via asyncpg (uses production pool)
├── triggers.py       # 5 trigger implementations + registry
├── retrieval.py      # Trigger chain orchestration → ActiveSubgraph
├── serialization.py  # Subgraph → token-budgeted text for LLM context
├── ingest.py         # Message → nodes/edges extraction (with pre-filter)
├── evolve.py         # Periodic graph maintenance (embeddings, decay, prune, synthesis)
└── feedback.py       # Post-response: track surfaced items, mark completions
```

## Database Tables

Created by migration `00004_graph_memory_tables.sql`:

### memory_nodes
Atomic facts: tasks, people, dates, feelings, raw data.
- `halfvec(1024)` embeddings (50% memory vs `vector(1024)`)
- HNSW index with `halfvec_cosine_ops`
- `source_message_id` FK to `messages` for provenance
- `last_activated_at` tracks recency for retrieval

### memory_edges
Bi-temporal relationships between nodes.
- `valid_from` / `valid_until` — corrections invalidate old edges, never delete
- `strength` — decays over time, reinforced when re-mentioned
- `decay_exempt` — protects structural edges (e.g., status connections)

### node_neighbors
Materialized cache for O(1) neighbor lookups during retrieval. Rebuilt after evolution cycles.

All tables have RLS policies scoped to `auth.uid() = user_id`.

## Data Flow

### 1. Context Retrieval (per message, ~100-200ms)

When `graph_context` appears in a pipeline's `context_rules.yaml` optional list:

1. `fetch_graph_context(user_id, message)` is called
2. Embeds the user message via OpenAI
3. Runs trigger chain → collects relevant node IDs
4. Loads full nodes + edges → `ActiveSubgraph`
5. Serializes to token-budgeted `<context>` block
6. Returns string (or `None` in shadow mode)

**Shadow mode** (`graph.yaml: shadow_mode: true`): The full retrieval runs and is logged, but the context is NOT injected into the LLM prompt. This lets you audit graph quality in Langfuse/structlog before going live. Set `shadow_mode: false` to activate.

### 2. Graph Ingest (post-processing, async)

After the pipeline responds, QStash dispatches `/jobs/process-graph`:

1. **Pre-filter**: Skip messages < 3 chars, emoji-only, punctuation-only
2. **Quick ingest**: LLM extracts nodes, edges, corrections from user message
3. **Embedding**: Generate halfvec embeddings for new nodes
4. **Feedback**: Detect which nodes the response surfaced or marked as done

### 3. Graph Evolution (periodic, not per-message)

`evolve_graph(user_id)` runs periodically (call from a cron job or admin endpoint):

1. Generate missing embeddings
2. Discover new connections via similarity
3. LLM synthesis: merges, contradictions, refinements
4. Edge decay (strength × 0.99, skips `decay_exempt`)
5. Prune weak edges (invalidate below threshold)
6. Rebuild neighbor cache

## Triggers

Defined in `config/triggers.yaml`. Independent triggers run in parallel; dependent triggers (like `graph_walk`) run after.

| Trigger | Type | What it finds |
|---------|------|---------------|
| semantic | vector_search | Nodes similar to message embedding |
| temporal | date_proximity | Date nodes within ±7 days + their connections |
| open_items | status_query | Nodes connected to "not done" status node |
| recent | recency | Nodes activated in last 24 hours |
| suppression | status_query | Nodes connected to "surfaced" (don't repeat) |
| graph_walk | walk | Neighbors of all found nodes (1-hop) |

## Serialization

`serialize_subgraph()` converts the active subgraph into LLM-readable text within a token budget (`max_context_tokens: 2000`). Sections are priority-ranked:

1. **OPEN** (priority 90) — Things not done yet, with deadline info
2. **SCHEDULE** (priority 85) — Events today/tomorrow
3. **RECENTLY SURFACED** (priority 80) — Don't repeat these
4. **PEOPLE** (priority 50) — Named entities with connections
5. **RECENT CONTEXT** (priority 20) — Recently activated nodes

Sections are included highest-priority-first until the token budget is exhausted. Individual sections are truncated line-by-line if they exceed remaining budget.

## Pre-Ingest Filter

`should_ingest(message)` skips LLM ingest calls for trivial input:
- Messages < 3 characters
- Messages with no alphanumeric characters (pure emoji)
- Messages that are only punctuation

This saves ~$0.001 per skipped message and prevents noise nodes.

## Prompt Hardening

`prompts/graph_ingest.md` includes defenses for production input:

- **Context-free data drops**: "4085551234" → one node, no invented relationships
- **Large/document input**: Extract only key facts, max `quick_max_nodes`
- **Instruction injection**: User message is treated as DATA, not directives
- **Conversational messages**: "hey", "thanks" → empty arrays

## Configuration

### config/graph.yaml
```yaml
ingest:
  quick_model: gpt-4.1-nano    # Fast/cheap model for extraction
  quick_max_nodes: 10           # Max nodes per message
  recent_nodes_context: 30      # Existing nodes shown to ingest LLM

retrieval:
  max_subgraph_nodes: 50        # Cap on retrieved subgraph size

serialization:
  max_context_tokens: 2000      # Token budget for context block

evolution:
  edge_decay_factor: 0.99       # Strength multiplier per cycle
  edge_decay_min: 0.01          # Below this → prune (invalidate)
  dedup_threshold: 0.9          # Cosine similarity for merging

shadow_mode: true               # Log context but don't inject
```

### config/triggers.yaml
Defines the trigger chain. Each trigger has `type`, `params`, and optional `depends_on`.

## Graceful Degradation

| Failure | Behavior |
|---------|----------|
| Graph tables don't exist | `fetch_graph_context` returns None, pipeline runs without |
| Ingest LLM fails | Warning logged, graph misses this message |
| Ingest returns invalid JSON | Falls back to empty node list |
| Retrieval exception | Returns None, pipeline runs without graph context |
| Embedding API fails | Semantic trigger returns empty, others still work |
| Graph empty (new user) | All triggers return empty, serialization produces nothing |
| Evolution fails | Graph stays in current state, next cycle catches up |

## Logging

All graph operations log with `trace_id` for cross-system tracing. Following the plan's PII rules:

**Logged**: user_id, node counts, edge counts, latencies, trigger names, skip reasons
**Never logged**: node content, edge content, user message text

Key log events:
- `graph.ingest.done` — nodes_created, edges_created, corrections_applied
- `graph.ingest.skipped` — reason (too_short, no_alphanumeric, punctuation_only)
- `graph.retrieval.done` — triggers_fired, nodes_in_subgraph, edges_in_subgraph
- `graph.serialization.done` — sections_included, tokens_used, tokens_budget
- `graph.feedback.done` — surfaced_count, completed_count
- `graph.evolution.done` — full EvolutionResult

## Cost Estimate

| Operation | Cost per call | When | Monthly (100 users, 20 msgs/day) |
|-----------|--------------|------|----------------------------------|
| Ingest (gpt-4.1-nano) | ~$0.001 | Per message | ~$60 |
| Retrieval (SQL only) | $0 | Per message | $0 |
| Embedding (text-embedding-4) | ~$0.0001 | Per message | ~$6 |
| Evolution (gpt-4.1-nano) | ~$0.01 | Daily per user | ~$30 |
| Feedback (gpt-4.1-nano) | ~$0.001 | Per message | ~$60 |

**Total graph overhead: ~$156/month for 100 active users.**

## Integration Points

### Files modified (existing)
- `orchestrator/types.py` — `graph_context: str | None` on Context
- `orchestrator/context.py` — graph_context loader + message passing
- `orchestrator/engine.py` — graph_context in prompt variables
- `orchestrator/config_models.py` — GraphConfigModel, TriggersConfigModel
- `config/context_rules.yaml` — graph_context optional on 8 intents
- `config/jobs.yaml` — process_graph in dispatch_map
- `prompts/system.md` — `<context>` tag handling instructions
- `db/supabase.py` — graph tables in delete_user_data
- `db/redis.py` — upgraded to native async client
- `api/chat.py` — graph_context in context_fields log
- `jobs/router.py` — /jobs/process-graph endpoint
- Pipeline YAMLs — process_graph post_processing on brain_dump, status_done, conversation, emotional

### Files created (new)
- `src/graph/` — 8 module files
- `src/tools/graph_tools.py` — fetch_graph_context tool
- `src/jobs/process_graph.py` — post-processing job
- `config/graph.yaml` — graph system config
- `config/triggers.yaml` — trigger chain config
- `prompts/graph_ingest.md` — ingest prompt
- `prompts/graph_evolve.md` — evolution prompt
- `supabase/migrations/00004_graph_memory_tables.sql` — schema

## Going Live Checklist

1. Apply migration: `00004_graph_memory_tables.sql` to Supabase
2. Deploy backend with new code
3. Verify shadow mode logging in Langfuse/structlog
4. Audit graph quality: do nodes/edges make sense for real messages?
5. Set `shadow_mode: false` in `config/graph.yaml`
6. Push — graph context now injected into LLM prompts
7. Add evolution cron job (daily, per-user)
8. Monitor costs via Langfuse token tracking

## Redis Async Upgrade (infrastructure)

As part of this integration, `backend/src/db/redis.py` was upgraded:
- **Before**: Sync `upstash_redis.Redis` wrapped in `asyncio.to_thread()` for every call
- **After**: Native `upstash_redis.asyncio.Redis` — direct async, no thread pool overhead
- `rate_limit_check` uses Redis pipelining: SET NX + INCR in 1 HTTP roundtrip (was 2)
