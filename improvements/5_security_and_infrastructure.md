# 5. Security & Infrastructure: Hardening the Foundation

## The Core Challenge: Scalability and Extreme Privacy
Unspool is designed to act as a "second brain." The data stored inside it—unfiltered thoughts, fears, tasks, relationships, and financial trackers—is far more sensitive than a standard to-do list.

Furthermore, the architectural choices must support both the fast, real-time nature of the Hot Path (conversational Agent A) and the heavy, asynchronous processing of the Cold Path (Agent B).

## The Solution: Robust Pooling, Strict Policies, and Zero-Trust Telemetry

### 1. Database Connection Management (Serverless Readiness)
**The Issue:** `backend/src/db/supabase.py` manages an `asyncpg` connection pool manually in the application memory. If this backend is deployed to a serverless environment (like Vercel, AWS Lambda, or Cloud Run), every single invocation spins up a new instance, creating a new connection pool. This will rapidly exhaust Supabase's Postgres connection limits, leading to timeouts and crashes.

**The Fix:**
*   **Supavisor (Transaction Pooling):** Route all Postgres connections through Supabase's built-in connection pooler (Supavisor) configured for **Transaction pooling** rather than Session pooling. This allows thousands of serverless functions to multiplex over a small number of physical database connections.
*   **The HTTP Fallback:** For standard CRUD operations triggered by the frontend (if bypassing the local-first sync), use the PostgREST API (via the Supabase Python/JS client) which operates over stateless HTTP. Reserve `asyncpg` purely for the heavy, long-running QStash background workers (like the Graph Archiver) where transaction blocks are strictly necessary.

### 2. Bulletproof Row-Level Security (RLS)
**The Issue:** Relying on application-level filtering (e.g., ensuring every Python SQL query includes `WHERE user_id = $1`) is highly prone to human error. A single bug or a hallucinated tool argument from the LLM could accidentally expose one user's private thoughts to another.

**The Fix (Zero-Trust Postgres):**
*   With the transition to an Event-Sourced Graph, all user data lives in three tables (`event_stream`, `graph_nodes`, `graph_edges`).
*   Enforce **strict Postgres Row-Level Security (RLS)** on these tables.
*   The policy must guarantee that a row is only readable/writable if `auth.uid() = user_id`. 
*   **Why it matters:** Even if a developer writes a flawed `SELECT * FROM graph_nodes` query in the backend, or if the LLM attempts a malicious SQL injection, the Postgres engine will physically refuse to return or mutate rows belonging to other users. The database acts as an unbreakable firewall.

### 3. Telemetry and PII Scrubbing
**The Issue:** The backend currently uses Langfuse for LLM observability. Logging raw prompts—which contain the user's unclassified brain dumps, medical worries, and financial data—to a third-party observability platform is a massive privacy liability.

**The Fix:**
*   **Metadata Only (Default):** Configure the telemetry pipeline to log *only* metadata by default. Log token usage, latency, tool names called, HTTP status codes, and error stack traces. Do not log the `<user_input>` or `<thought>` block text.
*   **Opt-In Debugging with Masking:** If prompt logging is strictly necessary for resolving a bug, it must be explicitly opted-in by the user. Even then, pass the text through a lightweight local NLP scanner (like **Microsoft Presidio**) before transmission to mask sensitive fields (e.g., automatically replacing "My SSN is 123-45-678" with "My SSN is [REDACTED]").

### 4. Background Job Idempotency (QStash Security)
**The Issue:** The Cold Path relies heavily on QStash to process graph mutations asynchronously. If a QStash webhook is retried due to a network blip, the system might ingest the same brain dump twice, duplicating nodes and edges.

**The Fix:**
*   **Idempotency Keys:** Every event in the `event_stream` must be written with a unique idempotency key (typically the hash of the `MessageId` + `Timestamp`). 
*   Before the background Archiver attempts to parse a message into Graph Nodes, it checks the database using this key. If the event has already been processed, it gracefully skips execution. This guarantees that network retries never corrupt the user's graph.