# 1. Database Architecture: The Event-Sourced Knowledge Graph

## The Core Challenge: The Categorization Trap
The fundamental problem in building an ADHD-friendly assistant is that **categorization is friction**. Traditional apps force users to decide: *Is this a Task? A Note? A Calendar Event? A Habit to track?*

For a user doing a brain dump, a single sentence might be all of these simultaneously:
> "My thesis is stressing me out, I need to email Sarah about chapter 3 by Friday, also she still owes me $20."

Currently, the Unspool backend splits this into relational tables (`items`, `events`, `trackers`, `notes`) and a parallel graph (`memory_nodes`). This requires the AI to fragment the user's unified thought into different database schemas, which destroys the context of how these pieces relate.

## The Solution: A Unified Knowledge Graph via Event Sourcing

We must completely abandon rigid tables for "items" or "notes". Instead, everything is an unclassified **Node**, connected by semantic **Edges**, driven by an immutable **Event Stream**.

### 1. The Event Stream (The Single Source of Truth)
Instead of updating rows, we append events. This preserves the history of the user's changing mind.
* **Table:** `event_stream`
* **Schema:** `id`, `user_id`, `event_type` (e.g., `MessageReceived`, `NodeCreated`, `EdgeAdded`), `payload` (JSONB), `created_at`.
* **Why?** If a user changes a deadline from Tuesday to Wednesday, we don't overwrite Tuesday. We append a `DeadlineUpdated` event. This allows the system to recognize meta-patterns: *"The user has delayed this specific task 4 times."*

### 2. The Unified Graph (The Materialized View)
Background workers read the `event_stream` and project it into read-optimized Graph tables.
* **Table: `graph_nodes`**
  * Represents *entities*: "Sarah", "Buy milk", "Thesis", "Stressed".
  * Schema: `id`, `user_id`, `content` (text), `node_type` (optional soft tag like 'concept', 'action', 'metric'), `embedding` (vector).
* **Table: `graph_edges`**
  * Represents *relationships* and *state*.
  * Schema: `id`, `user_id`, `source_node_id`, `target_node_id`, `edge_type` (e.g., `HAS_DEADLINE`, `IS_STATUS`, `RELATES_TO`, `TRACKS_METRIC`), `weight`, `metadata` (JSONB for things like values or timestamps).

### How This Solves Categorization
There is no longer a concept of a "Task" in the database. 
* A **Note** is simply a Node sitting alone in the graph.
* A **Task** is just a Node that happens to have an `IS_STATUS` edge pointing to an `OPEN` node.
* A **Calendar Event** is a Node with a `HAS_DATETIME` edge.
* If a user suddenly adds a deadline to a random Note, the system simply draws a new `HAS_DATETIME` edge. It magically "becomes" a Task/Event without any database schema migrations or table shuffling.

---

## Deep Dive: Querying and Entity Resolution

Without rigid tables, how does the system know what the user is asking for, and how does it know *which* item they mean? 

### 1. "What are my deadlines?" (Querying by Edge Structure)
When the user asks this, the AI doesn't query a `tasks` table. Instead, it queries the graph for a specific **structural signature**.
* **Agent Intent:** Finds all nodes that are currently `OPEN` and have a `HAS_DEADLINE` edge in the future.
* **Under the hood view (Postgres/SQL over the Graph):**
  ```sql
  SELECT n.content, e_deadline.metadata->>'date' as deadline 
  FROM graph_nodes n
  JOIN graph_edges e_status ON n.id = e_status.source_node_id
  JOIN graph_edges e_deadline ON n.id = e_deadline.source_node_id
  WHERE e_status.edge_type = 'IS_STATUS' 
    AND e_status.target_node_id = 'OPEN_NODE_ID'
    AND e_deadline.edge_type = 'HAS_DEADLINE'
    AND (e_deadline.metadata->>'date')::timestamp > NOW();
  ```
* **The View Concept:** You can create standard Postgres Views (or Materialized Views) on top of the graph to make this easy for the backend to query. A `vw_active_deadlines` view would just run the query above, presenting a flat, familiar table to the LLM agent without permanently locking the data into that shape.

### 2. "How many cigs did I smoke?" (Tracking Metrics)
Instead of a separate `trackers` table, metrics are just nodes with quantitative edges.
* **The Ingestion:** When the user says "smoked 3 cigs today", the background Archiver creates/finds the Node "cigs", creates a Node for the event ("smoked 3 cigs"), and draws a `TRACKS_METRIC` edge between them, storing `{ "value": 3, "unit": "count", "date": "..." }` in the edge's metadata.
* **The Query:** The agent queries the graph for all `TRACKS_METRIC` edges pointing to the "cigs" node within the specified time range, summing the values in the metadata.
* **The View Concept:** A `vw_metrics` view can aggregate all `TRACKS_METRIC` edges grouped by the target node's content ("cigs", "water", "spending").

### 3. "The exam is done" (Entity Resolution & Ambiguity)
How do we know *which* exam the user is talking about without fuzzy matching strings?
This relies on **Semantic Search + Graph Neighborhoods**.

**Step 1: The Search (Agent calls `query_graph("exam", filter={"status": "OPEN"})`)**
* The system generates an embedding for "exam".
* It runs a vector similarity search across all `graph_nodes` owned by the user, explicitly filtering for nodes that have an `IS_STATUS` edge pointing to `OPEN`.
* Because it's an embedding search, it understands that "midterm", "final test", or "biology exam" are semantically identical to "exam".

**Step 2: Resolving Ambiguity**
* **Case A (1 Match):** The search returns exactly one open node: `UUID-123` ("Biology Midterm"). The agent immediately proceeds to Step 3.
* **Case B (Multiple Matches):** The search returns two open nodes: `UUID-123` ("Biology Midterm") and `UUID-456` ("History Final Exam"). 
  * The agent **does not guess**.
  * The agent responds: *"Which one? Biology Midterm or History Final?"*
  * The user replies: *"History."*
  * The agent searches again with the new context and locks onto `UUID-456`.

**Step 3: The Mutation (Agent calls `mutate_graph(node_id="UUID-123", action="UPDATE_EDGE", edge_type="IS_STATUS", new_target="DONE")`)**
* The backend appends a `StatusUpdated` event to the `event_stream`.
* The view projector updates the graph, moving the `IS_STATUS` edge from `OPEN` to `DONE`.

### Summary of Graph Views (The "Lens" approach)
Because the core data is a graph, we can project it into specific "Lenses" (Postgres Views) depending on what the LLM needs to see:
1. **`vw_actionable`**: Nodes with `IS_STATUS = OPEN` (Tasks, unread articles, pending errands).
2. **`vw_timeline`**: Nodes with a `HAS_DATETIME` edge (Calendar events, deadlines, reminders).
3. **`vw_metrics`**: Nodes connected by `TRACKS_METRIC` edges (Habits, spending, mood).
4. **`vw_people`**: Nodes of type `person` and the edges connecting them to the user's tasks or feelings.

This architecture means the user never organizes their life; they just type. The background Archiver weaves the graph, and the foreground Agent uses structural Lenses to instantly retrieve answers based on the *shape* of the connections rather than rigid folders.