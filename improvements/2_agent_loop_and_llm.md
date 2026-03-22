# 2. Agent Loop & LLM Usage: The Dual-Agent Architecture

## The Core Challenge: Conflicting Objectives
The current system (`run_agent` in `loop.py`) relies on a single LLM loop to do two very different jobs simultaneously:
1. Be a warm, fast, empathetic conversationalist with low latency.
2. Be a meticulous data-entry clerk, strictly parsing JSON arguments for 17 database tools.

These goals conflict. When an LLM is prompted to be conversational, it often hallucinates tool schemas. When forced into strict JSON generation, it becomes robotic and latency spikes. Furthermore, preventing the LLM from "thinking out loud" (to keep the chat clean) severely degrades its reasoning capabilities.

## The Solution: The Hot/Cold Asynchronous Architecture

We must decouple the user's perception of speed (chatting) from the system's need for rigor (graph building and pattern recognition). We do this by splitting the architecture into a **Hot Path** (foreground) and a **Cold Path** (background).

---

### The Hot Path: Agent A (The Conversationalist)
This agent interacts directly with the user in real-time. It prioritizes latency, tone, and immediate context retrieval.

* **Technology:** **LangGraph** or **LlamaIndex Workflows** to manage the state machine, allowing deterministic cycles of Thought -> Tool Use -> Final Response.
* **Model:** GPT-4o or Claude 3.5 Sonnet (optimized for speed and reasoning).
* **The `<thought>` Scratchpad:** The system prompt *requires* the agent to open every turn with a `<thought>` XML block. Here, it safely reasons about the user's emotional state, plans its response, and decides what context it lacks.
  * *Example:* `<thought>User is stressed about 'the exam'. I only see 'midterms' in recent context. I should query the graph for open exams before I ask them to clarify.</thought>`
* **Backend Interception:** The Python backend streams the response but intercepts and hides anything between `<thought>` and `</thought>` from the user interface.
* **Tool Access (Read-Heavy, Write-Light):** 
  * `query_graph(semantic_query, filters)`: Pulls specific nodes (people, active tasks).
  * `mutate_graph(node_id, action)`: Used *only* for explicit commands like "mark done" or "delete".

### The Cold Path: Agent B & Background Cron Jobs
This is where the magic happens. The user never waits for this. It runs asynchronously via a task queue (e.g., **QStash** or **Celery**).

#### 1. The Post-Message Archiver (Immediate Cold Path)
Triggered the second a user sends a message.
* **Model:** GPT-4o-mini (fast, cheap, highly reliable at formatting).
* **Feature:** OpenAI **Structured Outputs** (`response_format`).
* **The Job:** It takes the raw user message and translates it into Graph Mutations (identifying new Nodes, drawing new Edges, extracting intelligent dates).
* **Intelligent Date Parsing:** Instead of relying on rigid Regex, the LLM converts fuzzy dates ("next Friday after my shift") into exact ISO8601 timestamps based on the user's timezone (passed in the prompt context) and draws a `HAS_DEADLINE` edge to the concept node.

#### 2. The Nightly Synthesizer (Periodic Cold Path)
A cron job runs at 3 AM (user's local time) to perform deep synthesis, completely detached from the chat loop.
* **Consolidation:** Looks at all nodes created in the last 24 hours. Does the user have 3 different nodes for "Call Mom", "Speak to mother", and "Ring Mom"? The synthesizer merges these into a single "Mom" entity node and aggregates the edges.
* **Pattern Recognition:** Analyzes the `event_stream`. *Did the user push the 'gym' task 5 days in a row?* The synthesizer creates a new `meta_observation` node: "User consistently delays morning workouts."
* **Personalization Profile:** Updates the user's system prompt context. If the user yelled at the bot for using emojis, the nightly synthesizer updates the core `Profile` view to strictly forbid emojis.

#### 3. Proactive Cache Warming (The "Lens" Builder)
While we don't ask users for categories, human lives naturally cluster into them (Work, Health, Finances).
* **The Clustering Job:** Once a week, a background LLM job runs a clustering algorithm (e.g., K-Means on the Node Embeddings) to discover emergent, un-prompted categories unique to the user.
* **Dynamic Views:** If it detects a tight cluster of nodes related to "Thesis", "Advisor", and "Lab", it creates a cached "Lens" (a named graph view).
* **The Benefit:** When the user asks, "How is my thesis going?", Agent A doesn't have to do a slow, multi-hop graph traversal. It just queries the pre-cached "Thesis Lens", drastically reducing latency and token costs.

---

### Handling Edge Cases & Scenarios

#### Scenario 1: Ambiguous Mutations
* **User:** "I finished it." (No context)
* **Agent A (Hot Path):** Uses `<thought>` to recognize missing target. It queries recent history. If recent history shows "Writing the email", it asks: "Did you finish the email?". It *does not guess and execute*.

#### Scenario 2: High-Volume Brain Dump
* **User:** "I need to call sarah, buy milk, cancel the netflix sub, and why is my back hurting, also the project is due on the 12th."
* **Agent A (Hot Path):** Acknowledges the dump warmly. *"Got it all. That's a lot on your plate."* (0.5s latency).
* **Agent B (Cold Path):** Spends 10 seconds meticulously parsing the text into 4 distinct Tasks, 1 Physical Symptom node, and 1 Person entity, drawing the correct temporal edges. The UI's "Dynamic Plate" populates them one by one as they process, giving a satisfying visual completion.

#### Scenario 3: Diary Entries & "Non-Actionable" Data
* **User:** "I felt really sad today when I saw that movie."
* **Agent A:** Validates the emotion.
* **Agent B:** Extracts an `Emotion` node ("Sadness") and a `Concept` node ("Movie"), linking them with an `EXPERIENCED_DURING` edge. Over months, the Nightly Synthesizer might notice a pattern and gently suggest, "I've noticed certain types of media affect your mood heavily."

### Summary of Best Practices
1. **Never mutate on a guess:** Force the LLM to retrieve exact UUIDs before writing.
2. **Move extraction out of the hot loop:** Use OpenAI Structured Outputs in background workers for 100% schema compliance.
3. **Cache by clustering, not by folders:** Let algorithms find the shape of the user's life (The Thesis, The Renovation) and cache those sub-graphs to make retrieval instantaneous.