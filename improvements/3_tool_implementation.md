# 3. Tool Implementation: Precision, Consolidation, and Integrations

## The Core Challenge: Tool Sprawl and Hallucinated Mutations
The current `backend/src/agent/tools.py` exposes 17+ highly specific tools (`save_items`, `mark_done`, `update_item`, `get_upcoming`, etc.). 

1. **Cognitive Load:** Exposing 17 tools consumes massive amounts of the LLM's context window just in tool descriptions, increasing the likelihood of selecting the wrong tool.
2. **Dangerous Mutations:** Tools like `mark_done` rely on the LLM passing a raw string (e.g., "finished the email"), which the backend then attempts to resolve using `fuzzy_match_item`. This is incredibly dangerous. If the user has two emails, the backend might guess the wrong one, silently marking a critical task as completed.
3. **Integration Maintenance:** Building bespoke integrations for Google Calendar, Apple Calendar, Outlook, Gmail, and Notion requires maintaining distinct OAuth flows, API schemas, and webhook listeners, which is a massive engineering overhead.

---

## Part 1: Consolidation and Exact Addressing

With the transition to a Knowledge Graph architecture (where everything is a Node and Edge), we can collapse the native tool surface area drastically. The conversational agent only needs a few highly reliable primitives.

### 1. `query_graph` (Read)
Instead of `get_upcoming`, `get_tracker_summary`, or `search`, the agent uses one unified search tool powered by vector embeddings and structured filters.
* **Input Schema (Pydantic):** 
  * `semantic_query` (str): e.g., "Sarah's birthday party"
  * `edge_filters` (dict, optional): e.g., `{"edge_type": "HAS_DEADLINE", "timeframe": "next_48h"}`
  * `node_type` (str, optional): e.g., "metric", "person"
* **Output:** Returns exact Node IDs, text content, and their immediate connected edges.

### 2. `mutate_graph` (Write)
Instead of `update_item` or `mark_done`, the agent uses a unified mutation tool that requires **Exact Addressing**.
* **Input Schema (Pydantic):** 
  * `node_id` (UUID - strictly required)
  * `action` (Enum: `ADD_EDGE`, `REMOVE_EDGE`, `UPDATE_METADATA`)
  * `target` (str): e.g., "STATUS: DONE"
* **The Workflow (Fixing the Fuzzy Match):**
  1. User: *"I finished the thesis draft."*
  2. Agent `<thought>`: *I need to find the node for the thesis draft, get its ID, and add a DONE edge.*
  3. Agent calls `query_graph(semantic_query="thesis draft")`.
  4. Backend returns: `[{"id": "uuid-1234", "content": "Write thesis draft"}]`.
  5. Agent calls `mutate_graph(node_id="uuid-1234", action="ADD_EDGE", target="STATUS: DONE")`.
* If the user's request is ambiguous (e.g., it returns two "thesis" nodes), the agent's `<thought>` loop catches this, refuses to call `mutate_graph`, and asks the user for clarification.

### 3. Strict Validation Boundary
Every tool must be backed by a strict Pydantic model. If the LLM passes an invalid payload (e.g., it forgets the `node_id`), the `ValidationError` is caught by the backend and returned directly to the LLM as a tool result: `{"error": "Missing required field 'node_id'. You must use query_graph to find the ID first."}`. The state machine allows the LLM to read the error and try again seamlessly.

---

## Part 2: 3rd Party Integrations (The Low-Maintenance Strategy)

Integrating with external tools (Calendars, Emails, CRMs) is the fastest way to drain engineering resources. For an ADHD assistant, the goal isn't to build a better calendar app; it's to have read/write access to the user's existing life.

### The Strategy: Standardized Protocols over Bespoke APIs

Instead of building a Google OAuth flow, an Outlook flow, and an Apple flow, we leverage open standards and integration hubs.

#### 1. Universal Calendar Sync (CalDAV / ICS)
* **The Problem:** Bi-directional sync with Google/Apple/Outlook APIs is notoriously flaky and requires aggressive token refreshing.
* **The Low-Maintenance Fix:**
  * **Read (Ingestion):** The user provides an `.ics` subscription link (from Google, Apple, or Outlook). A daily background cron job (or QStash worker) fetches the `.ics`, parses the events, and creates `Event Nodes` in the Unspool graph. 
  * **Write (Export):** Unspool generates a unique, read-only `.ics` link for the user (`unspool.app/feed/{secure_token}.ics`). The user subscribes to this in their native calendar app. Whenever Unspool creates a deadline or scheduled action, it appears on their phone automatically. 
  * **Why it's better:** Zero OAuth maintenance. The native calendar app handles the heavy lifting of UI and push notifications.

#### 2. Email Triage via "Forwarding" (SMTP Ingestion)
* **The Problem:** Giving an AI read access to a user's entire Gmail inbox via OAuth is a massive security liability and requires expensive API polling.
* **The Low-Maintenance Fix:** 
  * Give each user a unique forwarding address (e.g., `maya.123@add.unspool.app`).
  * When a user gets a flight itinerary, a bill, or a stressful email they can't deal with right now, they just forward it to that address.
  * **The Pipeline:** The email hits a serverless webhook (like SendGrid Inbound Parse or Postmark), which dumps the text into the `event_stream`. The background Archiver (Agent B) processes the text, extracts the actionable tasks ("Pay bill by Friday"), and creates the necessary Graph Nodes.
  * **Why it's better:** The user actively curates what the AI sees. No privacy violations of reading personal emails, and zero API syncing required.

#### 3. Leveraging MCP (Model Context Protocol)
Anthropic recently open-sourced the **Model Context Protocol (MCP)**, which standardizes how AI agents connect to external data sources.
* **The Future-Proof Strategy:** Instead of building custom API connectors for Notion, Slack, or GitHub, run an MCP Server. As the open-source community builds MCP connectors for these platforms, Unspool can plug them in instantly. The LLM simply sees them as standard tools it can call, keeping the core Unspool backend thin and completely agnostic to 3rd party API changes.

### Summary
By consolidating internal operations to exact Graph primitives (`query_graph`, `mutate_graph`) and relying on universal standards (`.ics` feeds, Email Forwarding, MCP) for the outside world, Unspool maintains a massive capability footprint with a tiny, easily maintainable codebase.