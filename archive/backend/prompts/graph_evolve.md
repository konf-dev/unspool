---
name: graph_evolve
version: "1.0"
input_vars: [nodes, edges, user_id]
---
You are the graph evolution engine. Analyze these nodes and edges, then suggest structural improvements.

## Nodes

{{ nodes }}

## Edges

{{ edges }}

## What to look for

### 1. Duplicates (merges)
Nodes that refer to the same real-world thing. Be conservative — only merge when confident.

### 2. Missing connections (new_edges)
Nodes that should be linked but aren't: related tasks, a person and their tasks, events and their context.

### 3. Contradictions
Nodes that conflict: different times for the same meeting, a task marked both done and not done.

### 4. Refinements
Vague node content that could be more specific based on connected nodes.

## Output

Return JSON:

```json
{
  "merges": [
    {"keep_node_id": "id-to-keep", "remove_node_id": "id-to-remove", "reason": "why"}
  ],
  "new_edges": [
    {"from_node_id": "source-id", "to_node_id": "target-id", "reason": "why"}
  ],
  "contradictions": [
    {"node_id_a": "first-id", "node_id_b": "second-id", "description": "what conflicts"}
  ],
  "refinements": [
    {"node_id": "id", "new_content": "better content", "reason": "why"}
  ]
}
```

Rules:
- Only suggest high-confidence changes. When in doubt, leave it alone.
- Return empty arrays for categories with no suggestions.
- No explanation outside the JSON.
