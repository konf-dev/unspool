# Generic Primitives Architecture

## Core Insight

User input is unstructured brain dumps. The system structures it progressively:

```
User brain dump (unstructured)
    → Main LLM (respond + rough tool calls, multiple primitives per message)
    → Async ingest (richer extraction, cross-referencing, linking)
    → Evolution (dedup, merge, pattern detection, connections)
```

The LLM doesn't need to perfectly categorize. It throws data at the right primitives loosely. Async layers clean up, deduplicate, and connect. Same info CAN exist in multiple primitives — that's a feature, not a bug.

## Seven Primitives

### 1. Items (existing)
Tasks, to-dos, commitments. The LLM decides urgency, energy, deadlines.

### 2. Events (new)
Anything with a time — meetings, reminders, deadlines, recurring.
- Unifies: Google Calendar events + user-mentioned events + scheduled reminders + recurring events
- RRULE for recurrence (RFC 5545)
- Source tracking: user | google | system

### 3. Trackers + Entries (new)
Anything logged over time — fuel, sleep, expenses, habits, medications.
- LLM auto-creates trackers on first mention
- Entries are data points with value + optional note
- Flexible types: numeric, boolean, text, currency

### 4. Notes (new)
Freeform structured information — outlines, lists, references, recipes, flight details.
- Embedded for semantic search
- AI-tagged for retrieval
- Not actionable (that's what items are for)

### 5. Scheduled Actions (new)
Future-triggered behaviors — nudges, check-ins, questions, surfacing.
- The "deferred execution" primitive
- QStash dispatches at execute_at time
- RRULE for recurring actions
- LLM decides what action to schedule and when

### 6. Collections (new)
Ephemeral groupings — grocery list, packing list, reading list.
- LLM creates/manages transparently (user never sees "collections")
- Items linked by reference
- Dissolve when no longer relevant

### 7. Graph Memory (existing)
Relationships, facts, patterns between all of the above.
- Nodes can reference items, events, trackers, notes
- Edges capture relationships the flat tables can't
- Evolution layer connects things across primitives

## Tools

| Tool | Primitives | Description |
|------|-----------|-------------|
| `save_items` | Items | Already exists. Tasks, to-dos, commitments. |
| `mark_done` | Items | Already exists. Complete an item. |
| `pick_next` | Items, Events | Already exists. Extended to consider events. |
| `search` | All | Already exists. Extended to search all primitives. |
| `get_upcoming` | Items, Events | Already exists. Extended to include events. |
| `get_progress` | Items, Tracker Entries | Already exists. Extended with tracker data. |
| `update_item` | Items | Already exists. |
| `remove_item` | Items | Already exists. |
| `save_preference` | User Profile | Already exists. |
| `decompose_task` | Items | Already exists. |
| `remember` | Graph | Already exists. Signals async ingest. |
| `save_event` | Events | NEW. Create/update events, reminders, recurring. |
| `log_entry` | Trackers, Entries | NEW. Record a data point. Auto-creates tracker. |
| `get_tracker_summary` | Trackers, Entries | NEW. Summarize recent entries for patterns. |
| `save_note` | Notes | NEW. Store freeform information. |
| `schedule_action` | Scheduled Actions | NEW. Defer any behavior to a future time. |
| `manage_collection` | Collections | NEW. Create, add to, list, dissolve groupings. |

## Async Consolidation (background job)

Runs after each message (or periodically). Responsibilities:
- Link items to graph nodes that represent the same thing
- Auto-create trackers when the LLM logs entries for unnamed patterns
- Deduplicate near-identical items/events
- Promote frequently mentioned things into recurring events
- Update event times when the user provides corrections
- Dissolve stale collections

## Design Principles

1. **No intent classification.** The LLM uses whatever tools fit. Multiple tools per message is the default.
2. **Overlap is fine.** "Rent due on the 1st" can be an item AND a recurring event AND a graph node. Async layers reconcile.
3. **LLM decides the use case.** No hardcoded categories, units, or patterns. The AI interprets.
4. **JSONB metadata everywhere.** Escape hatch for anything we didn't anticipate.
5. **Progressive structuring.** Brain dump → rough extraction → async refinement → evolution.
