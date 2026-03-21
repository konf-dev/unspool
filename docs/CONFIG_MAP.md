# Config Map (Updated March 2026)

Unspool has transitioned from a fixed-pipeline architecture to an autonomous **Single-Agent Loop**. User intents are no longer mapped to static YAML pipelines; instead, the agent uses tool-calling to achieve the user's goals dynamically.

## Core Agent Loop

The system is driven by `backend/src/agent/loop.py`, which uses a monolithic system prompt (`backend/prompts/agent_system.md`) to manage interaction logic, tool selection, and context retrieval.

### Interaction Flow
1. **Context Assembly:** `assemble_context` gathers the user profile, recent messages, relevant graph memory, and calendar events.
2. **System Prompting:** `build_system_prompt` injects the context and the current time into the base instructions.
3. **Streaming & Tool Selection:** The agent streams its response. If it identifies an action (saving a task, searching history, etc.), it calls the appropriate tool.
4. **Reliability Buffering:** The loop buffers text responses during tool rounds to ensure that confirmations (e.g., "Saved!") are only sent if the underlying tool succeeds.
5. **Post-Processing:** Certain actions trigger background jobs via QStash (e.g., `process-message` for embeddings and graph ingestion).

---

## Active Tools

| Tool | Purpose | File |
|------|---------|------|
| `save_items` | Extracts and persists new tasks/ideas | `backend/src/tools/item_tools.py` |
| `update_item` | Modifies existing task details (dates, text) | `backend/src/tools/item_tools.py` |
| `remove_item` | Deprioritizes or "forgets" an item | `backend/src/tools/item_tools.py` |
| `mark_done` | Marks a task as completed | `backend/src/tools/item_tools.py` |
| `pick_next` | Selects ONE task for the user to focus on | `backend/src/tools/momentum_tools.py` |
| `search` | Semantic search over tasks and memories | `backend/src/tools/search_tools.py` |
| `get_upcoming` | Lists upcoming deadlines as a narrative | `backend/src/tools/item_tools.py` |
| `schedule_action` | Queues future reminders or check-ins | `backend/src/tools/item_tools.py` |
| `remember` | Persists conversation facts to long-term memory | `backend/src/tools/graph_tools.py` |
| `log_entry` | Records measurable values for tracking | `backend/src/tools/tracker_tools.py` |
| `save_note` | Persists structured reference information | `backend/src/tools/note_tools.py` |

---

## Configuration Files (YAML)

While pipelines are removed, the following configuration files still drive specific logic:

| File | Purpose |
|------|---------|
| `gate.yaml` | Rate limits and safety gates |
| `scoring.yaml` | Parameters for urgency and task selection |
| `proactive.yaml` | Triggers for fresh AI greetings (welcome back, etc.) |
| `graph.yaml` | Rules for graph memory ingestion and evolution |
| `jobs.yaml` | Cron schedules for background maintenance |
| `patterns.yaml` | Rules for behavioral pattern detection |

## Dead/Legacy Content
- `backend/config/pipelines/` — REMOVED
- `backend/src/orchestrator/` — REMOVED
- `viz/` — Legacy (needs update to support agent-loop)
