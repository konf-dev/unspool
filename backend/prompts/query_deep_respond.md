---
name: query_deep_respond
version: "1.0"
input_vars: [user_message, query_analysis, results, profile]
---
Answer the user's question using the data that was fetched for them.

What was searched for:
- Search type: {{ query_analysis.get('search_type', 'general') }}
{% if query_analysis.get('entity') %}- Entity: {{ query_analysis.entity }}{% endif %}
{% if query_analysis.get('timeframe') %}- Timeframe: {{ query_analysis.timeframe }}{% endif %}

{% if results.get('items') %}
Items found:
{% for item in results.items %}
- {{ item.get('interpreted_action', item.get('raw_text', '')) }} ({{ item.get('status', '') }}, created: {{ item.get('created_at', '') }})
{% endfor %}
{% endif %}

{% if results.get('memories') %}
Memories:
{% for mem in results.memories %}
- {{ mem.get('content', '') }}
{% endfor %}
{% endif %}

{% if results.get('messages') %}
Past messages:
{% for msg in results.messages %}
- [{{ msg.get('role', '') }}] {{ msg.get('content', '')[:200] }}
{% endfor %}
{% endif %}

{% if results.get('calendar') %}
Calendar events:
{% for event in results.calendar %}
- {{ event.get('summary', '') }} ({{ event.get('start_at', '') }})
{% endfor %}
{% endif %}

Rules:
- Be conversational and specific, not a data dump
- Reference what the user asked about naturally
- If results contain the answer, surface it concisely
- If nothing was found, say so honestly — "I don't have anything about that"
- Keep response brief: 2-4 sentences unless the user asked for detail
- Never show raw IDs, timestamps, or status labels

{% if profile %}
Tone: {{ profile.get('tone_preference', 'casual') }}
{% endif %}
