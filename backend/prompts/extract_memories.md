---
name: extract_memories
version: "1.0"
input_vars: [user_messages]
---
Extract factual information about the user from these messages. Facts are things like:
- Personal details (name, location, job, school, relationships)
- Preferences (doesn't work on Sundays, prefers mornings, hates phone calls)
- Ongoing projects or commitments (thesis topic, job search, recurring activities)
- People they mention regularly (supervisor, mom, friends by name)

Messages:
{% for msg in user_messages %}
- {{ msg }}
{% endfor %}

Return each fact on its own line, prefixed with "- ". Only include clear, confident facts — not speculation.
If no meaningful facts can be extracted, return exactly: NONE
