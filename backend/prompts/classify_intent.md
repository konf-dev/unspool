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
{{ msg.role }}: <user_input>{{ msg.content }}</user_input>
{% endfor %}
{% endif %}

Disambiguation:
- query_search vs query_upcoming: If the user references a *specific* item, person, or event by name → query_search. If asking about a time range or "what's coming up" → query_upcoming.
- emotional vs status_done: Positive feelings ("I got so much done!", "feeling great") → emotional. Reporting completion of a *specific task* → status_done.
- meta vs onboarding: User has recent conversation history → meta. No recent messages → onboarding.
- onboarding vs conversation: Bare greeting ("hi") with no recent messages → onboarding. With recent messages → conversation.
- status_done vs conversation: status_done requires the user to reference completing a specific task. General statements about activities are conversation.

User message: <user_input>{{ user_message }}</user_input>

Respond with a JSON object:
{"intent": "<intent_name>", "confidence": <0.0-1.0>}
