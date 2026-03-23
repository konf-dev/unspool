---
name: consolidate_memories
version: "1.0"
input_vars: [nodes]
---
Review these graph nodes from a user's knowledge graph. Identify duplicates, contradictions, and outdated information.

## Nodes
{% for node in nodes %}
- [{{ node.id }}] <user_input>{{ node.content }}</user_input> (type: {{ node.node_type }}, created: {{ node.created_at }})
{% endfor %}

For each node, decide:
- **keep**: the node is unique and still valid
- **merge**: two or more nodes refer to the same thing — combine into one
- **remove**: the node is superseded, contradicted, or no longer relevant

Return a JSON object:
```json
{
  "keep": ["id1", "id2"],
  "merge": [
    {
      "source_ids": ["id3", "id4"],
      "merged_content": "the combined content"
    }
  ],
  "remove": ["id5"]
}
```

Be conservative — when in doubt, keep the node. Only remove when clearly superseded or contradicted.
