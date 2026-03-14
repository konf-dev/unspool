---
name: query_deep_respond
version: "1.1"
input_vars: [user_message, query_analysis, results, profile]
---
Answer the user's question using the data that was fetched for them.

{% if query_analysis is mapping %}
What was searched for:
- Search type: {{ query_analysis.get('search_type', 'general') }}
{% if query_analysis.get('entity') %}- Entity: {{ query_analysis.entity }}{% endif %}
{% if query_analysis.get('timeframe') %}- Timeframe: {{ query_analysis.timeframe }}{% endif %}
{% endif %}

{% if results is mapping %}
{% if results.get('items') %}
Items found:
{% for item in results.items %}
{% if item is mapping %}
- {{ item.get('interpreted_action', item.get('raw_text', '')) }} ({{ item.get('status', '') }})
{% endif %}
{% endfor %}
{% endif %}

{% if results.get('memories') %}
Memories:
{% for mem in results.memories %}
{% if mem is mapping %}
- {{ mem.get('content', '') }}
{% endif %}
{% endfor %}
{% endif %}

{% if results.get('messages') %}
Past messages:
{% for msg in results.messages %}
{% if msg is mapping %}
- [{{ msg.get('role', '') }}] {{ msg.get('content', '')[:200] }}
{% endif %}
{% endfor %}
{% endif %}

{% if results.get('calendar') %}
Calendar events:
{% for event in results.calendar %}
{% if event is mapping %}
- {{ event.get('summary', '') }} ({{ event.get('start_at', '') }})
{% endif %}
{% endfor %}
{% endif %}
{% endif %}

Rules:
- Be conversational and specific, not a data dump
- Reference what the user asked about naturally
- If results contain the answer, surface it concisely
- If nothing was found, say so honestly — "I don't have anything about that"
- Keep response brief: 2-4 sentences unless the user asked for detail
- Never show raw IDs, timestamps, or status labels

{% if profile is mapping %}
Tone: {{ profile.get('tone_preference', 'casual') }}
{% endif %}
