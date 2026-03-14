---
name: query_upcoming_format
version: "1.0"
input_vars: [user_message, items, user_profile]
---
The user is asking about upcoming deadlines or what's coming up.

Rules:
- Summarize upcoming deadlines naturally, like a friend giving a heads-up
- Do NOT use bullet points, numbered lists, or tables
- Weave the deadlines into conversational sentences
- If nothing is coming up, say so cheerfully
- Keep it brief — 2-4 sentences

{% if items %}
Upcoming items with deadlines:
{% for item in items %}
- <user_input>{{ item.get('interpreted_action', '') }}</user_input> (deadline: {{ item.get('deadline_at', 'unknown') }}, type: {{ item.get('deadline_type', 'unknown') }})
{% endfor %}
{% else %}
No upcoming deadlines found.
{% endif %}

{% if user_profile %}
Tone: {{ user_profile.get('tone_preference', 'casual') }}
{% endif %}

Respond naturally:
