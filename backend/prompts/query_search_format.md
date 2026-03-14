---
name: query_search_format
version: "1.0"
input_vars: [user_message, results, query, user_profile]
---
The user searched for something specific. Present what you found conversationally.

Rules:
- Reference what the user asked about
- Present results naturally, not as a list
- If nothing was found, say so and offer to help them capture it
- Keep it brief — 2-3 sentences

User asked about: <user_input>{{ query }}</user_input>

{% if results %}
Found items:
{% for item in results %}
- {{ item.get('interpreted_action', '') }} (status: {{ item.get('status', 'unknown') }})
{% endfor %}
{% else %}
No matching items found.
{% endif %}

{% if user_profile %}
Tone: {{ user_profile.get('tone_preference', 'casual') }}
{% endif %}

Respond naturally:
