---
name: analyze_query
version: "1.1"
input_vars: [user_message, recent_messages, profile]
---
The user is asking a question or searching for something. Determine what data we need to fetch to answer it.

User's message: {{ user_message }}

{% if recent_messages %}
Recent conversation for context:
{% for msg in recent_messages[-5:] %}
{{ msg.role }}: {{ msg.content }}
{% endfor %}
{% endif %}

Return ONLY a raw JSON object (no markdown, no code fences, no explanation) with this schema:

{"search_type": "entity | temporal | semantic | status | general", "entity": "name or null", "timeframe": "last_week | last_month | last_N_days | null", "sources": ["items", "memories", "messages", "calendar"], "text_query": "search terms or null", "status_filter": "open | done | all", "limit": 10}

Guidelines:
- If user mentions a person, place, or project by name → search_type: "entity", set entity field
- If user asks about a time period → set timeframe
- "did I ever..." or "have I mentioned..." → sources: ["items", "memories"], status_filter: "all"
- "what's open" / "what's pending" / "reminders" → sources: ["items"], status_filter: "open"
- "what did I finish" / "what's done" → sources: ["items"], status_filter: "done"
- "what's on my calendar" → sources: ["calendar"]
- When in doubt, search items and memories with status "all"
- Keep limit low (5-10)
