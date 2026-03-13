---
name: conversation_extract
version: "1.0"
input_vars: [user_message, message, recent_messages]
---
Extract any implicit tasks or actionable items from this casual conversation. The user may not realize they're assigning themselves a task.

Examples:
- "I told my boss I'd finish the slides" -> extract "finish slides" with soft deadline
- "We should really fix the fence sometime" -> extract "fix the fence" with no deadline
- "Just chatting about my day" -> extract nothing (empty array)

{% if recent_messages %}
Recent conversation:
{% for msg in recent_messages[-5:] %}
{{ msg.role }}: {{ msg.content }}
{% endfor %}
{% endif %}

Current message: {{ message }}

Respond with a JSON object only:
{
  "items": [
    {
      "raw_text": "original phrase from message",
      "interpreted_action": "clear action statement",
      "deadline_type": "hard|soft|none",
      "deadline_at": null,
      "energy_estimate": "low|medium|high"
    }
  ]
}

If no implicit tasks, return: {"items": []}
