---
name: emotional_detect
version: "1.0"
input_vars: [user_message, message]
---
Detect the emotional level in the user's message.

Levels:
- "low": Mild frustration, minor annoyance, slightly overwhelmed but functional
- "medium": Noticeably stressed, overwhelmed, struggling to cope, anxiety about tasks
- "high": Crisis mode, breakdown, feeling completely unable to function, deep distress

User message: {{ message }}

Respond with a JSON object only:
{"level": "low|medium|high", "reasoning": "brief explanation"}
