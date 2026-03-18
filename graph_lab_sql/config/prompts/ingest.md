Extract atomic nodes, edges, and corrections from the user's message. The user has ADHD — they may brain-dump multiple things at once, mix tasks with feelings, or bury a deadline inside a tangent. That's expected.

Current datetime: {{ current_datetime }}

## Node granularity

Each node is ONE atomic concept — a task, person, date, descriptor, or feeling. Break compound sentences into separate nodes and connect them with edges.

- Resolve ALL relative dates to ISO format. "Friday" → the next Friday from current datetime. "tomorrow" → the day after. "next week" → Monday of next week.
- Date nodes should contain ONLY the ISO date: "2026-03-20", not "Friday March 20"
- Status nodes: use "not done" for open tasks, "done" for completed ones
- Keep node content short and clear — 1-4 words typically

## Matching existing nodes

These nodes already exist in the user's graph. If the message references something that matches, set `existing_match` to the node's ID instead of creating a duplicate. Match synonyms too ("mom" = "my mother", "rent" = "pay rent").

Existing nodes:
{{ existing_nodes }}

## Corrections

When the user updates or corrects previously stated information, extract a correction. Corrections are changes to EXISTING facts — not new information.

Types:
- **explicit**: User clearly states a change — "actually", "wait no", "I meant", "meeting moved to", "changed to"
- **implicit**: User states new info that contradicts earlier info (detect but mark as implicit)
- **retroactive**: User reveals past info was wrong (detect but mark as retroactive)

Example corrections:
- "meeting moved to 3pm" → correction: target="meeting with team", old_value="2pm", new_value="3pm", type=explicit
- "actually the deadline is next Friday not Thursday" → correction: target="deadline", old_value="2026-03-19", new_value="2026-03-20", type=explicit

## Examples

**Example 1 — Brain dump:**
Message: "I need to email my advisor about thesis deadline extension. also rent is due friday for real, late fee after that"
Current date: 2026-03-16

```json
{
  "nodes": [
    {"content": "email advisor", "existing_match": null},
    {"content": "thesis", "existing_match": null},
    {"content": "deadline extension", "existing_match": null},
    {"content": "rent", "existing_match": null},
    {"content": "2026-03-20", "existing_match": null},
    {"content": "hard deadline", "existing_match": null},
    {"content": "late fee", "existing_match": null}
  ],
  "edges": [
    {"from": "email advisor", "to": "thesis"},
    {"from": "email advisor", "to": "deadline extension"},
    {"from": "email advisor", "to": "not done"},
    {"from": "rent", "to": "2026-03-20"},
    {"from": "rent", "to": "hard deadline"},
    {"from": "rent", "to": "late fee"},
    {"from": "rent", "to": "not done"}
  ],
  "edge_updates": [],
  "corrections": []
}
```

**Example 2 — Completion:**
Message: "done with rent"
Existing nodes include: rent (id: abc-123)

```json
{
  "nodes": [
    {"content": "done", "existing_match": null}
  ],
  "edges": [
    {"from": "rent", "to": "done"}
  ],
  "edge_updates": [
    {"from": "rent", "to": "not done", "new_strength": 0}
  ],
  "corrections": []
}
```

**Example 3 — Correction:**
Message: "wait the meeting got moved to 3pm, not 2"
Existing nodes include: team meeting (id: def-456), 2pm (id: ghi-789)

```json
{
  "nodes": [
    {"content": "3pm", "existing_match": null}
  ],
  "edges": [
    {"from": "team meeting", "to": "3pm"}
  ],
  "edge_updates": [],
  "corrections": [
    {
      "target_content": "team meeting",
      "old_value": "2pm",
      "new_value": "3pm",
      "correction_type": "explicit"
    }
  ]
}
```

**Example 4 — Emotional/casual:**
Message: "ugh I can't focus today, been scrolling my phone for hours"

```json
{
  "nodes": [
    {"content": "low energy", "existing_match": null},
    {"content": "can't focus", "existing_match": null}
  ],
  "edges": [
    {"from": "low energy", "to": "can't focus"}
  ],
  "edge_updates": [],
  "corrections": []
}
```

## Constraints

- Maximum {{ max_nodes }} nodes per message
- If the message is purely conversational ("hey", "thanks", "lol"), return empty arrays
- When matching existing nodes, use the exact ID from the existing nodes list
- Edge `from` and `to` fields reference node content strings (or existing node content)
- Only return corrections when you're confident the user is changing existing information

## User message

{{ message }}

Return a JSON object with `nodes`, `edges`, `edge_updates`, and `corrections` arrays. No explanation, just JSON.
