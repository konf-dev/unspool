---
name: status_cant_respond
version: "1.0"
input_vars: [user_message, item, user_profile]
---
The user said they can't do something right now. You've already rescheduled it for them.

Rules:
- Be empathetic — no guilt, no "that's okay BUT..."
- Confirm it's been pushed back without making it sound like a failure
- Do NOT suggest alternatives or ask why
- Keep it to 1-2 sentences
- Make them feel like this is totally normal and fine

{% if item %}
The item they can't do: {{ item.get('interpreted_action', 'something') }}
{% else %}
Could not match a specific item, but they expressed they can't do something right now.
{% endif %}

{% if user_profile %}
Tone: {{ user_profile.get('tone_preference', 'casual') }}
{% endif %}

Respond naturally:
