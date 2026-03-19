# Eval Report — 2026-03-19

## Summary

First E2E product behavior eval run against the live Railway deployment.

- **25 scenarios** across 6 categories
- **18 passed, 7 failed (72%)**
- Judge: `qwen2.5-coder:32b` (local Ollama)
- Target: `https://api.unspool.life` (production)

## Results by Category

| Category | Passed | Failed | Scenarios |
|----------|--------|--------|-----------|
| Habit tracking | 5/5 | 0 | track_cigarettes_daily, log_cigarettes_numeric, track_spending_currency, log_meds_boolean, get_fuel_summary |
| Reminders & scheduling | 3/5 | 2 | remind_2_hours_laundry, meeting_friday_3pm, rent_monthly_recurring |
| Date/time parsing | 1/5 | 4 | check_thesis_3_days |
| Collections | 3/3 | 0 | add_grocery_items, whats_on_grocery_list, create_packing_list |
| Proactive/recurring | 3/4 | 1 | nudge_thesis_every_3_days, check_sleep_next_monday, stop_tracking_cigarettes |
| Cross-feature | 3/3 | 0 | cross_fuel_and_car_service, cross_meeting_and_prep, cross_grocery_and_shopping_reminder |

## Failures — Detailed

### BUG-1: Agent uses `save_items` instead of `schedule_action` for reminders

**Scenarios:** `remind_call_bank_wednesday`

The agent saved "call the bank" as a task via `save_items` instead of scheduling a reminder via `schedule_action`. The response said "I'll remind you" but no actual reminder was scheduled.

**Root cause:** The tool descriptions for `schedule_action` vs `save_items` may not be clear enough about when to use which. The agent defaults to saving items.

**Impact:** High — reminders are a core feature. Users will think they set a reminder but nothing will fire.

**Fix:** Improve `schedule_action` tool description to explicitly say "use this for reminders" and add negative guidance to `save_items`: "do NOT use for reminders — use schedule_action instead."

---

### BUG-2: Agent doesn't schedule recurring check-ins

**Scenario:** `ask_meds_every_morning`

The agent responded "I'll ask you about your meds every morning" but called no tool at all — no `schedule_action` with rrule. The intent was acknowledged but not executed.

**Root cause:** Same as BUG-1 — the agent doesn't reliably reach for `schedule_action`. Possibly the phrase "ask me" doesn't trigger tool use because the agent treats it as a conversational commitment rather than an action.

**Impact:** High — recurring check-ins are a key differentiator.

**Fix:** Same as BUG-1 (tool description tuning). May also need a system prompt instruction: "When the user asks you to do something at a future time, ALWAYS call schedule_action. Never just promise to do it."

---

### BUG-3: Server error on dentist appointment

**Scenario:** `dentist_tuesday_1030`

Response: "sorry, something went wrong on my end. try again?"

**Root cause:** Unknown — needs Railway log investigation. Possibly a tool execution error in `save_event` or a timeout.

**Impact:** Medium — intermittent server errors erode trust.

**Fix:** Check Railway logs / Langfuse trace for this specific request. Look for the error in the `tool.execute` span.

---

### BUG-4: Date/time args not verifiable (Langfuse ingestion gap)

**Scenarios:** `exam_on_the_20th`, `thesis_end_of_april`, `bus_pass_expires_next_week`, `submit_by_friday_5pm`

The agent called the right tools (confirmed via SSE) and the responses were correct ("I've added your exam on the 20th"), but the Langfuse trace didn't contain the tool call data when fetched. This means `args_contain` assertions (e.g. "deadline_at contains 20") couldn't be verified.

**Root cause:** Langfuse async ingestion timing. The 45-second wait wasn't enough for some traces, or the `agent.run` observation output wasn't fully written yet.

**Impact:** Low for product quality (the agent is doing the right thing), but the eval framework can't fully verify args.

**Fix options:**
1. Increase Langfuse settle time to 60-90s
2. Re-fetch traces that have missing observations in a second pass
3. Accept SSE-only tool presence for `save_items` and skip args assertions when Langfuse data is unavailable

---

### BUG-5: No current time in system prompt (FIXED in this sprint)

**Context:** The agent had no concept of current time. "Remind me in 5 minutes" produced wrong datetimes. "What time is it?" returned "I can't access the current time."

**Status:** Fixed — current time now injected into system prompt using user's timezone. Browser timezone auto-detected and synced to profile.

## Bugs to Fix Next Sprint

| ID | Priority | Summary | Fix |
|----|----------|---------|-----|
| BUG-1 | P0 | Reminders saved as items, not scheduled | Tune tool descriptions |
| BUG-2 | P0 | Recurring check-ins not scheduled | Tune tool descriptions + system prompt |
| BUG-3 | P1 | Server error on save_event | Investigate Railway/Langfuse logs |
| BUG-4 | P2 | Langfuse ingestion timing for eval args | Increase settle time or add retry pass |

## What Worked Well

- **Tracking (5/5):** The agent correctly uses `log_entry` for all numeric/boolean/currency tracking. No lectures about smoking.
- **Collections (3/3):** `manage_collection` called correctly for groceries and packing lists. No unnecessary confirmations.
- **Cross-feature (3/3):** Multi-intent messages ("spent 450 on fuel, also remind me...") correctly dispatched to multiple tools.
- **Cancellation:** "Stop asking me about cigarettes" correctly handled without setting up new tracking.
- **E2E framework:** The two-phase approach (send all → wait → fetch Langfuse → judge) works reliably with throttling.

## Framework Notes

- Langfuse rate limits hit at ~75 requests in quick succession (25 traces + 50 observations). Fixed with 0.5s throttle between traces and 0.3s between observations.
- `qwen2.5-coder:32b` is a reasonable judge for response quality but occasionally strict. 7B model was unusable (contradicted itself).
- SSE tool name fallback is critical — Langfuse data wasn't available for ~20% of traces within the 45s window.
