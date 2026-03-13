---
name: classify_intent
version: "1.1"
input_vars: [user_message, recent_messages]
---
Classify the user's message into exactly one intent.

Possible intents:
- brain_dump: User is capturing tasks, ideas, reminders, or things to do
- query_next: User is asking what to do next or what's on their plate
- query_search: User is searching for something specific they previously mentioned
- query_upcoming: User is asking about upcoming deadlines or scheduled items
- status_done: User is marking something as completed
- status_cant: User is skipping, postponing, or snoozing something
- emotional: User is venting, expressing feelings, or seeking emotional support
- meta: User is asking about the system, how it works, or requesting help
- onboarding: User is new or asking introductory questions about what they can do
- conversation: General chat that doesn't fit other categories

{% if recent_messages %}
Recent conversation for context:
{% for msg in recent_messages[-5:] %}
{{ msg.role }}: {{ msg.content }}
{% endfor %}
{% endif %}

User message: {{ user_message }}

Respond with a JSON object:
{"intent": "<intent_name>", "confidence": <0.0-1.0>}
