---
name: brain_dump_extract
version: "1.1"
input_vars: [user_message, profile]
---
Extract actionable items from the user's brain dump. The user has ADHD — they may be rambling, mixing tasks with thoughts, or dumping everything at once. That's fine.

For each item, determine:
- raw_text: The original text fragment
- interpreted_action: A clear, concise action statement
- deadline_type: "hard" (fixed external date — rent, exam, meeting), "soft" (flexible social expectation — reply to someone, return a call), or "none"
- deadline_at: ISO 8601 datetime if mentioned or inferable, null otherwise
- energy_estimate: "low" (quick/easy, under 15 min), "medium" (moderate, 15-45 min), "high" (significant effort, deep focus needed). Judge by the actual task, not individual words.
- urgency_score: 0.0 to 1.0. Consider deadline proximity, real-world consequences of delay, and whether external parties are waiting. 0.0 = no urgency, 1.0 = must happen today.

User message: <user_input>{{ user_message }}</user_input>

{% if profile and profile.get('timezone') %}
User timezone: {{ profile.timezone }}
{% endif %}

Respond with a JSON object:
{
  "items": [
    {
      "raw_text": "...",
      "interpreted_action": "...",
      "deadline_type": "none",
      "deadline_at": null,
      "energy_estimate": "medium",
      "urgency_score": 0.1
    }
  ],
  "non_actionable_notes": ["any thoughts/feelings that aren't tasks"]
}
