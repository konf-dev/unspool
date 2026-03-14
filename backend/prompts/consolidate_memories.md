---
name: consolidate_memories
version: "1.0"
input_vars: [memories]
---
Review these stored memories about a user. Identify duplicates, contradictions, and outdated information.

## Memories
{% for mem in memories %}
- [{{ mem.id }}] {{ mem.content }} (created: {{ mem.created_at }}, confidence: {{ mem.confidence }})
{% endfor %}

For each memory, decide:
- **keep**: the memory is unique and still valid
- **merge**: two or more memories say the same thing — combine into one
- **remove**: the memory is superseded, contradicted, or no longer relevant

Return a JSON object:
```json
{
  "keep": ["id1", "id2"],
  "merge": [
    {
      "source_ids": ["id3", "id4"],
      "merged_content": "the combined fact"
    }
  ],
  "remove": ["id5"]
}
```

Be conservative — when in doubt, keep the memory. Only remove when clearly superseded or contradicted.
