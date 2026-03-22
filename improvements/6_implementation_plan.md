# 6. Implementation Plan: Rebuilding Unspool

## The Strategy: "V2 Greenfield"
Given the fundamental shift in the underlying data model (from Destructive CRUD to an Event-Sourced Graph) and the shift in the AI architecture (from a single loop to a Dual-Agent Hot/Cold path), an incremental refactor of the existing codebase will result in a fragile "Frankenstein" system.

**Recommendation:** We start a clean "v2" directory structure alongside the current codebase. We use the current codebase purely as a reference for prompts and API keys. We build v2 from the ground up, ensuring every layer strictly adheres to the new principles.

---

## 1. Hosting & Infrastructure
We will continue utilizing the modern serverless/managed stack, which is highly scalable and cost-effective.

*   **Frontend:** **Vercel** (Fast global edge CDN for the React PWA).
*   **Backend:** **Railway** (For hosting the FastAPI Python backend. Perfect for long-running state machines like LangGraph and handles background worker loads better than Vercel serverless functions).
*   **Database & Auth:** **Supabase** (Postgres + `pgvector` + GoTrue Auth).
*   **Job Queue & KV:** **Upstash** (Using QStash for the Cold Path webhooks/cron jobs, and Upstash Redis for rate-limiting and fast KV caching).
*   **Local-First Sync Engine:** **PowerSync**. 
    *   *What is it?* It's a cloud service that sits between Supabase and the user's browser. It reads Postgres logical replication and syncs it to a local SQLite database in the browser.
    *   *Cost:* PowerSync has a generous **Free Tier** (Developer plan) that handles up to 10,000 monthly tracked users. If the app scales, paid tiers start around $49/month. This is extremely cost-effective for achieving zero-latency offline support.

---

## 2. The V2 File Structure Vision

We will enforce a strict separation of concerns.

```text
unspool-v2/
├── backend/
│   ├── src/
│   │   ├── api/                 # FastAPI endpoints (Hot Path entry points)
│   │   │   ├── chat.py          # The SSE streaming endpoint
│   │   │   └── webhooks.py      # Ingesting QStash, Email, ICS
│   │   ├── core/                # The Event-Sourced Database Layer
│   │   │   ├── events.py        # Event stream appending
│   │   │   ├── graph.py         # Graph projection and vector search (SQLAlchemy/SQLModel)
│   │   │   └── rls.py           # Postgres Row-Level Security definitions
│   │   ├── llm/                 # Provider-Agnostic LLM Layer
│   │   │   ├── protocol.py      # Abstract base classes
│   │   │   └── openai.py        # OpenAI implementation
│   │   ├── agents/
│   │   │   ├── hot_path/        # The Conversationalist
│   │   │   │   ├── state.py     # LangGraph state definitions
│   │   │   │   ├── nodes.py     # LangGraph nodes (Thought, Tool, Reply)
│   │   │   │   └── tools.py     # Only 2 tools: query_graph, mutate_graph
│   │   │   └── cold_path/       # The Archiver & Synthesizer
│   │   │       ├── extractor.py # OpenAI Structured Outputs logic
│   │   │       ├── synthesis.py # The Nightly Cron logic
│   │   │       └── lenses.py    # K-Means clustering for views
│   │   └── integrations/        # 3rd Party
│   │       ├── ics_feed.py      # Generating & Parsing Calendars
│   │       └── mcp_server.py    # Model Context Protocol endpoints
│   └── supabase/
│       └── migrations/          # V2 clean schema (event_stream, nodes, edges)
└── frontend_v2/                 # PWA & Local-First
    ├── src/
    │   ├── store/               # Zustand state management
    │   ├── sync/                # PowerSync / embedded SQLite setup
    │   ├── components/
    │   │   ├── stream/          # The Chat / Input layer
    │   │   └── plate/           # The Spatial Graph views
    │   └── lib/                 # Standardized SSE parsing
```

---

## 3. Phase-by-Phase Execution Plan

### Phase 1: The Bedrock (Database & Core API)
*   **What:** Design the Supabase schema. Write raw SQL migrations for `event_stream`, `graph_nodes` (with `pgvector`), and `graph_edges`.
*   **Crucial Step:** Implement strict Postgres Row Level Security (RLS) on all three tables. 
*   **Backend:** Set up FastAPI with SQLAlchemy 2.0 (async). Create the core Python functions to append to the `event_stream` and the database triggers that project those events into the `graph_nodes` and `graph_edges` tables.
*   **LLM Setup:** Build the provider-agnostic LLM registry. For now, it will only instantiate OpenAI clients, but the interface will be standard (e.g., `generate(messages, tools)`).
*   **Pitfall:** Projection latency. If a user says "I did the laundry", the event hits the stream. If the projection to the graph is too slow, the UI won't update instantly.
*   **Mitigation:** For simple mutations, we apply optimistic UI updates on the frontend, and the backend projections are handled synchronously within the transaction.

### Phase 2: The Cold Path (Agent B - The Archiver)
*   **What:** Build the background worker that parses raw brain dumps into the Graph.
*   **Backend:** Implement the `extractor.py` using **GPT-4o-mini** and OpenAI's `response_format` (Structured Outputs). Define the strict Pydantic schemas for `Node` and `Edge` extraction.
*   **Infrastructure:** Connect this to Upstash QStash. When an event is appended to `event_stream`, QStash triggers this worker.
*   **Pitfall:** The LLM hallucinates edges that don't make sense, or creates 5 different nodes for the same person.
*   **Mitigation:** The prompt must aggressively instruct the model to search existing nodes (via embedding similarity) *before* creating a new one. Provide few-shot examples of "good" graph structures in the system prompt.

### Phase 3: The Hot Path (Agent A - The Conversationalist)
*   **What:** The real-time chat loop.
*   **Backend:** Use **GPT-4o**. Replace the `while MAX_ROUNDS` loop with a **LangGraph** state machine.
    *   Node 1: `<thought>` generation and tool selection.
    *   Node 2: Tool execution (`query_graph`, `mutate_graph`).
    *   Node 3: Final streaming response.
*   **Pitfall:** Streaming latency spikes if LangGraph state transitions are heavy.
*   **Mitigation:** Stream tokens directly from the LLM callback handler within the LangGraph nodes, bypassing the state object for the actual character delivery.

### Phase 4: The Local-First Frontend
*   **What:** The split-pane PWA (Stream + Plate).
*   **Frontend:** Initialize a fresh Vite/React project. Integrate **PowerSync**. Configure it to pull the user's specific `graph_nodes` and `graph_edges` directly into an embedded SQLite database in the browser.
*   **UX:** Build the "Pull-Down Shelf" for mobile and the permanent right-pane for desktop. The Plate UI simply runs reactive SQL queries against the local SQLite DB (`SELECT * FROM graph_nodes WHERE status = 'OPEN'`).
*   **Pitfall:** Managing massive local databases on mobile devices.
*   **Mitigation:** The sync engine must be configured to only pull "Active" nodes (e.g., nodes modified in the last 30 days, or nodes with an `OPEN` edge). "Archived" graph data remains in Supabase and is only fetched when explicitly searched.

### Phase 5: Synthesis & Integrations
*   **What:** The "Magic" features.
*   **Backend:** Build the 3 AM QStash cron job (`synthesis.py`) to merge duplicate nodes and identify meta-patterns. Build the ICS feed generator so users can subscribe to their Unspool tasks in Google Calendar. Set up the custom email forwarding webhook.

---

## 4. The Final Vision

Imagine the user experience when this is done:
*   The user opens the app on a subway. It opens instantly because of PowerSync.
*   They type: *"Need to review chapter 3 by Friday, also call Mom, and why am I so tired today."*
*   They hit send. The Conversationalist (Agent A, GPT-4o) replies in 0.5 seconds: *"Got it. I've noted the deadlines and your energy levels. Take it easy today."*
*   The user swipes down. The Plate drops down. "Review Chapter 3" is sitting under Friday. "Call Mom" is sitting in Top of Mind. A new graph node for "Tiredness" has been logged against today's date.
*   They didn't have to click a single "Add Task" button, fill out a date picker, or wait for a loading spinner. The machine adapted to their mind, instantly.

---

## 5. Post-MVP Roadmap (After the Plan is Done)

Once V2 is stable:
1.  **Voice-First Interaction:** Implementing a continuous WebRTC voice connection (like OpenAI's Realtime API) so the user can literally just talk to their phone while walking, and the background Archiver continuously builds their Graph in real-time.
2.  **MCP Integration:** Plugging in the Model Context Protocol so Unspool can read their Slack messages or Notion docs without us writing custom OAuth logic.
3.  **Proactive Nudges:** Using the Push API to send notifications *based on context*, not just time. (e.g., "You have 30 minutes before your next meeting and 'Call Mom' is a 5-minute task. Want to do it now?")