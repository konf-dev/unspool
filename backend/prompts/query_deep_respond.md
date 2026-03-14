---
name: query_deep_respond
version: "1.2"
input_vars: [user_message, query_analysis, results, profile]
---
Answer the user's question using the data that was fetched for them.

{% if query_analysis is mapping %}
What was searched for:
- Search type: {{ query_analysis.get('search_type', 'general') }}
{% if query_analysis.get('entity') %}- Entity: {{ query_analysis.get('entity') }}{% endif %}
{% if query_analysis.get('timeframe') %}- Timeframe: {{ query_analysis.get('timeframe') }}{% endif %}
{% endif %}

{% if results is mapping %}
{% set found_items = results.get('items', []) %}
{% set found_memories = results.get('memories', []) %}
{% set found_messages = results.get('messages', []) %}
{% set found_calendar = results.get('calendar', []) %}

{% if found_items %}
Items found:
{% for item in found_items %}
{% if item is mapping %}
- {{ item.get('interpreted_action', item.get('raw_text', '')) }} ({{ item.get('status', '') }})
{% endif %}
{% endfor %}
{% endif %}

{% if found_memories %}
Memories:
{% for mem in found_memories %}
{% if mem is mapping %}
- {{ mem.get('content', '') }}
{% endif %}
{% endfor %}
{% endif %}

{% if found_messages %}
Past messages:
{% for msg in found_messages %}
{% if msg is mapping %}
- [{{ msg.get('role', '') }}] {{ msg.get('content', '')[:200] }}
{% endif %}
{% endfor %}
{% endif %}

{% if found_calendar %}
Calendar events:
{% for event in found_calendar %}
{% if event is mapping %}
- {{ event.get('summary', '') }} ({{ event.get('start_at', '') }})
{% endif %}
{% endfor %}
{% endif %}

{% if not found_items and not found_memories and not found_messages and not found_calendar %}
No matching data found.
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
