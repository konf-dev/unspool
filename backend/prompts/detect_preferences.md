---
name: detect_preferences
version: "1.0"
input_vars: [messages, current_profile, lookback_days]
---
Analyze this user's recent messages to infer their communication preferences.

## Recent messages (last {{ lookback_days }} days, user messages only)
{% for msg in messages[-20:] %}
- <user_input>{{ msg }}</user_input>
{% endfor %}

## Current profile preferences
{{ current_profile | tojson }}

Infer the following from their writing style:
- **tone**: casual (uses slang, "lol", informal), neutral (plain), or warm (expressive, "thanks!")
- **length**: terse (short messages), medium (default), or detailed (long, asks follow-ups)
- **pushiness**: gentle (default), moderate, or firm — based on how they respond to suggestions
- **uses_emoji**: true if they frequently use emoji, false otherwise
- **primary_language**: the language they write in most often (ISO 639-1 code)

Return a JSON object:
```json
{
  "tone": "casual | neutral | warm",
  "length": "terse | medium | detailed",
  "pushiness": "gentle | moderate | firm",
  "uses_emoji": true | false,
  "primary_language": "en",
  "confidence": 0.0-1.0
}
```

Only override current_profile values when you have clear evidence. If uncertain about a field, use the current value.
