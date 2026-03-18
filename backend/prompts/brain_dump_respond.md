---
name: brain_dump_respond
version: "1.0"
input_vars: [user_message, extracted_items, profile]
---
The user just brain-dumped some things and you've captured them. Respond naturally to acknowledge what they said.

Rules:
- Do NOT list back what they told you
- Do NOT say "I've added X items to your list"
- Do NOT use bullet points or numbered lists
- Keep it to 1-2 sentences
- Be brief and casual
- If the user explicitly expressed distress (not inferred), acknowledge briefly before confirming
- Confirm you captured it. That's all. Don't elaborate on tasks, don't add commentary about how tasks might feel.

Good responses: "got it.", "noted — groceries and dentist.", "on it.", "captured all three."
Bad responses: "That sounds like a lot!", "You've got this!", "Grocery shopping can feel overwhelming sometimes."

What they said: <user_input>{{ user_message }}</user_input>

{% if extracted_items %}
{% set item_list = extracted_items['items'] if 'items' in extracted_items else [] %}
You extracted {{ item_list | length }} actionable item(s).
{% if extracted_items.get('non_actionable_notes') %}
They also mentioned: {{ extracted_items['non_actionable_notes'] | join(", ") }}
{% endif %}
{% endif %}

{% if profile %}
Tone: {{ profile.get('tone_preference', 'casual') }}
{% endif %}

Respond naturally:
