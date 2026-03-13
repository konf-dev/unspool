---
name: brain_dump_extract
version: "1.0"
input_vars: [user_message, profile]
---
Extract actionable items from the user's brain dump. The user has ADHD — they may be rambling, mixing tasks with thoughts, or dumping everything at once. That's fine.

For each item, determine:
- raw_text: The original text fragment
- interpreted_action: A clear, concise action statement
- deadline_type: "hard" (fixed date/time), "soft" (flexible), or "none"
- deadline_at: ISO 8601 datetime if mentioned, null otherwise
- energy_estimate: "low" (quick/easy), "medium" (moderate effort), "high" (significant effort), or null if unclear

User message: {{ user_message }}

Respond with a JSON object:
{
  "items": [
    {
      "raw_text": "...",
      "interpreted_action": "...",
      "deadline_type": "none",
      "deadline_at": null,
      "energy_estimate": null
    }
  ],
  "non_actionable_notes": ["any thoughts/feelings that aren't tasks"]
}
