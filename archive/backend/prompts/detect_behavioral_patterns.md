---
name: detect_behavioral_patterns
version: "1.0"
input_vars: [completion_data, message_activity, current_patterns, lookback_days]
---
You are analyzing a user's behavioral data from the last {{ lookback_days }} days to find productivity patterns.

## Completion data (items marked done)
{{ completion_data | tojson }}

## Message activity (when they chat, volume per day)
{{ message_activity | tojson }}

## Previously detected patterns
{{ current_patterns | tojson }}

Analyze this data for patterns such as:
- Which days of the week are most/least productive
- Whether there are consistent dump times (when they brain-dump tasks)
- Whether completion rates correlate with message volume
- Avoidance patterns (types of tasks that sit longest)
- Energy patterns (bursts of completions vs long gaps)

Return a JSON object:
```json
{
  "patterns": [
    {
      "type": "productivity_timing | dump_timing | avoidance | energy_cycle | completion_rate",
      "description": "human-readable description of the pattern",
      "confidence": 0.0-1.0,
      "actionable": "what the AI could do differently based on this pattern"
    }
  ]
}
```

Only include patterns with confidence >= 0.5. If no clear patterns exist, return `{"patterns": []}`.
Do not fabricate patterns from insufficient data.
