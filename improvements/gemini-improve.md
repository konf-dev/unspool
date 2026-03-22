# Unspool Architecture & Codebase Deep Dive: Issues and Recommendations

This document outlines the structural, architectural, and implementation issues within the current Unspool codebase based on a deep analysis of the backend, frontend, and architectural guidelines. It proposes re-architecting solutions optimized for performance, accuracy, security, and an ADHD-friendly user experience.

## 1. Database & Core Data Architecture

### The Concept vs. Reality
The `docs/MEMORY_ARCHITECTURE.md` defines a brilliant "First Principles" concept: an immutable, append-only stream of "Thoughts" and "Actions" from which all views (memories, tasks, facts) are derived. This is meant to mimic how human memory works, prioritizing history and context.

**The Issue: Destructive CRUD**
*   **Where:** `backend/src/db/supabase.py`
*   **What's wrong:** The actual implementation is a standard CRUD (Create, Read, Update, Delete) system. It uses direct `UPDATE items SET ...` queries for mutations. 
*   **Why it's bad:** If a user corrects a deadline from Tuesday to Wednesday, the previous state is overwritten. This destroys the historical context of *how* and *why* a user's mind changed over time. For an ADHD assistant, the meta-pattern (e.g., "The user frequently reschedules this specific task") is just as important as the task itself.

**The Issue: Fragmented Data Models**
*   **Where:** `backend/src/db/supabase.py` and `backend/src/graph/db.py`
*   **What's wrong:** Data is split across relational tables (`items`, `events`, `trackers`, `notes`) and a completely separate parallel Graph memory system (`memory_nodes`, `memory_edges`).
*   **Why it's bad:** Keeping these in sync is complex, error-prone, and forces the LLM to use different tools to search different aspects of the user's life. 

**The Issue: Manual SQL Construction**
*   **Where:** `backend/src/db/supabase.py` (e.g., `set_clauses.append(f"{key} = ${i}")`)
*   **What's wrong:** Queries are constructed using raw string concatenation.
*   **Why it's bad:** It's highly brittle, difficult to maintain, and lacks type safety. 

### Recommendations
*   **Implement True Event Sourcing:** Create an immutable `event_stream` table. Every user message, tool call, and agent action is appended as an event. Use background workers (via QStash) to process these events and update "Materialized Views" (read-optimized tables for tasks, memories, etc.).
*   **Unified Knowledge Graph:** Stop treating "tasks" and "events" as different database tables from "memories". Collapse them into strongly-typed nodes within the Graph system. A "task" is just a node with a `type: task` and an edge connecting it to a `status: open` node.
*   **Adopt an Async ORM / Query Builder:** Integrate **SQLAlchemy 2.0 (async)** or **SQLModel** in Python to enforce strict types, handle migrations safely, and eliminate raw string SQL construction.

---

## 2. Agent Loop & LLM Usage

### The "No Scratchpad" Problem
**The Issue:**
*   **Where:** `backend/prompts/agent_system.md` and `backend/src/agent/loop.py`
*   **What's wrong:** The system prompt instructs the agent to be extremely brief, avoid motivational filler, and act like a calm friend. However, the LLM has no "private space" to reason about the user's input before generating its output.
*   **Why it's bad:** Because LLMs generate tokens sequentially, if they don't "think out loud", their logic suffers. Since they are forbidden from thinking out loud in the final response, they either rush to hallucinate tool calls or accidentally leak their reasoning into the chat, violating the persona.

**Recommendation:** 
*   **Implement `<thought>` blocks:** Instruct the agent to use a `<thought>` XML tag at the start of its turn to plan its multi-step tool use, evaluate the user's emotional state, and decide on a strategy. Modify `backend/src/agent/loop.py` to intercept and strip these tags before streaming the content to the frontend.

### Streaming & Concurrency Bottlenecks
**The Issue:**
*   **Where:** `backend/src/agent/loop.py`
*   **What's wrong:** The code buffers text chunks if it anticipates a tool call (`has_tool_calls`), waits for tools to execute in parallel, and then yields the text and tool results. 
*   **Why it's bad:** This causes severe stuttering in the UI. If a tool fails, buffered text might be dropped. The `while MAX_ROUNDS` loop is too rigid for complex, multi-step reasoning.

**Recommendation:**
*   **Use a State Machine:** Move to a deterministic graph-based state machine framework like **LangGraph** or **LlamaIndex Workflows**. This explicitly separates the routing logic, tool execution, and response generation into discrete nodes, making the streaming pipeline much more resilient and observable.

### Context Bloat vs. Precision Retrieval
**The Issue:**
*   **Where:** `backend/src/agent/context.py`
*   **What's wrong:** Every time a user sends a message, the system eagerly loads the user profile, the last 20 messages, and a massive chunk of graph context, injecting it all into the system prompt.
*   **Why it's bad:** This consumes a massive amount of context tokens ($$$) and degrades the LLM's attention span (the "lost in the middle" problem), making it miss recent, specific instructions.

**Recommendation:**
*   **Dynamic Tool-Based Retrieval:** Stop injecting everything upfront. Provide only the essential context (profile, current date/time, last 3 messages). Give the agent a `query_memory` or `search_graph` tool so it can proactively fetch specific task lists or past context *only* when the conversation requires it.

### Extraction vs. Conversation Conflict
**The Issue:**
*   **Where:** `backend/src/agent/tools.py`
*   **What's wrong:** The primary conversational LLM is responsible for being a warm friend *and* strictly parsing JSON arguments for 17 specific database tools.
*   **Why it's bad:** These are conflicting goals. A model tuned for conversational empathy often struggles with strict JSON schema adherence, leading to malformed arguments and failed tool calls.

**Recommendation:**
*   **Split the Workload:** Use a fast, cheap model (e.g., GPT-4o-mini) utilizing OpenAI's **Structured Outputs** (`response_format`) running in a separate node specifically to extract structured intents, deadlines, and entities from the user's raw message. Pass this structured data to the main conversational agent, freeing it to focus purely on tone and dialogue.

---

## 3. Tool Implementation Precision

### Tool Sprawl & Hallucinations
**The Issue:**
*   **Where:** `backend/src/agent/tools.py`
*   **What's wrong:** Exposing 17+ specific tools (`save_items`, `save_event`, `save_note`, `manage_collection`, `log_entry`, etc.).
*   **Why it's bad:** Too many tools dilute the model's focus, consume context space with descriptions, and increase the chance of the LLM picking the wrong tool for the job.

**Recommendation:**
*   **Consolidate:** Collapse CRUD operations into a single, polymorphic `upsert_entity` tool utilizing discriminated unions (e.g., an entity has a `type: 'task' | 'event' | 'note'`). 

### Dangerous "Fuzzy Matching" for Mutations
**The Issue:**
*   **Where:** `backend/src/tools/item_matching.py` (called by `mark_done` and `update_item` in `tools.py`).
*   **What's wrong:** Tools accept raw text (e.g., "finished the email") and the backend uses a fuzzy string match to guess which item the user meant to update.
*   **Why it's bad:** For an ADHD user relying on the system as their perfect external memory, the AI guessing and modifying the wrong task is disastrous and erodes trust.

**Recommendation:**
*   **Enforce Two-Step Exact Matching:** The agent must never mutate by string guess. If the user says "I finished the email," the agent must first use `search` to find the exact database UUID of the "email" task, and then pass that strict UUID to a `mutate_entity(id=UUID, status="done")` tool.

### Lack of Pydantic Validation
**The Issue:**
*   **Where:** `backend/src/agent/tools.py`
*   **What's wrong:** Tool handlers extract arguments using raw dictionary methods (`args.get("field")`).
*   **Why it's bad:** If the LLM hallucinates a parameter, provides the wrong type, or misses a required field, the code fails silently deeper in the stack or throws a generic exception, providing poor error feedback to the agent.

**Recommendation:**
*   **Pydantic everywhere:** Use Pydantic models to strictly validate incoming JSON tool arguments before they reach the execution logic. If validation fails, return the Pydantic error directly to the LLM so it can self-correct.

---

## 4. Frontend Architecture & UX

### Brittle SSE Parsing
**The Issue:**
*   **Where:** `frontend/src/lib/api.ts` -> `parseSSEEvents`
*   **What's wrong:** The code relies on brute-force string splitting (`data.split('}\n\n{')`) to handle malformed Server-Sent Events (SSE) chunks.
*   **Why it's bad:** This indicates the backend isn't flushing standard SSE formats correctly, and the frontend is applying a fragile band-aid. This leads to dropped messages or broken UI states.

**Recommendation:**
*   **Standardize SSE:** Ensure the backend strictly follows the `data: <json>\n\n` specification per yield. On the frontend, utilize standard SSE libraries without custom split hacks to ensure reliable token delivery.

### State Management Debt
**The Issue:**
*   **Where:** `frontend/src/components/ChatScreen.tsx`
*   **What's wrong:** The component is overloaded with complex logic: managing message history, streaming state, queued offline messages, tool execution status, and Easter eggs—all using `useState` and `useRef`.
*   **Why it's bad:** It makes the component massive, hard to test, and prone to race conditions (especially with rapid user input while offline).

**Recommendation:**
*   **Introduce Global State:** Use a state manager like **Zustand** or **Redux Toolkit** to decouple the chat logic, queue management, and streaming state from the React rendering cycle.

### Offline & "Local-First" Experience
**The Issue:**
*   **Where:** Frontend networking stack.
*   **What's wrong:** It queues messages in `localStorage` when offline, but the user cannot read past context or view their tasks reliably without a network connection.
*   **Why it's bad:** ADHD users often open apps in a sudden panic to jot something down or check what they need to do right now. If they are on a subway with no cell service, a spinning loading wheel is a critical failure.

**Recommendation:**
*   **Local-First Architecture:** Transition to a Local-First framework (e.g., **RxDB**, **WatermelonDB**, or **PowerSync/ElectricSQL** with SQLite in browser). The user's specific data partition syncs to the client's IndexedDB. Interactions, reads, and writes happen instantly against the local DB, and sync in the background when the network returns.

### ADHD-Friendly UX Additions
**The Issue:**
*   **Where:** UI Design.
*   **What's wrong:** A pure chat interface is highly linear, which places a heavy burden on working memory. To know their tasks, the user must ask "What's on my plate?" and read a text response.
*   **Why it's bad:** It forces the user to hold the current state of their life in their head.

**Recommendation:**
*   **Dashboard View:** Implement a split-screen or slide-over "Dashboard" panel. While the chat handles conversational input, the dashboard dynamically and automatically updates to show Active Tasks, Today's Calendar, and Current Trackers. This provides constant spatial context, offloading the cognitive burden from the user.

---

## 5. Security & Infrastructure

### Connection Pooling in Serverless
**The Issue:**
*   **Where:** `backend/src/db/supabase.py`
*   **What's wrong:** It manages an `asyncpg` connection pool manually in the application memory. 
*   **Why it's bad:** If the backend is deployed to a serverless environment (like Vercel, AWS Lambda, or Cloud Run), every invocation spins up a new instance, creating a new connection pool. This will rapidly exhaust the Supabase Postgres connection limits and crash the database.

**Recommendation:**
*   **Use a Proxy/HTTP Client:** Use Supabase's built-in connection pooler (Supavisor) configured for Transaction pooling. Alternatively, migrate to HTTP-based clients (PostgREST via the Supabase Python client) for standard CRUD, reserving heavy asyncpg connections purely for complex, long-running background jobs.

### Security Controls (RLS)
**The Issue:**
*   **Where:** Supabase database schema.
*   **What's wrong:** While some mentions of Row Level Security (RLS) exist, relying heavily on application-level filtering (e.g., `WHERE user_id = $1`) is risky.
*   **Why it's bad:** A single bug in the Python backend could accidentally expose another user's highly sensitive, personal thoughts.

**Recommendation:**
*   **Strict RLS:** Enforce Row Level Security (RLS) policies universally on all Supabase tables, tied to the authenticated user's JWT. The database layer itself must reject unauthorized access, creating a hard boundary even if the application code contains a flaw.