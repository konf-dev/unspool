# Background Jobs

## QStash Cron Jobs

Two consolidated cron jobs registered on startup (to stay within QStash free tier limits):

### `POST /jobs/hourly-maintenance` — Every hour
Runs sequentially, each catching its own errors:

1. **check_deadlines** — For each active user with items due within 24h:
   - Respects quiet hours (1-7 AM in user's timezone, wraps midnight)
   - Skips if `notification_sent_today = true`
   - Sends Web Push to all registered subscriptions
   - Single item: "Deadline approaching: {action}"
   - Multiple: "You have {count} items with deadlines in the next 24 hours"

2. **execute_actions** — Safety-net poll for overdue `scheduled_actions`:
   - Claims pending actions with `run_at <= NOW()`
   - Executes by type: `nudge` → push notification, others → queued proactive message
   - Handles rrule recurrence: calculates next occurrence, creates new action, dispatches via QStash `dispatch_at` if within 7 days

3. **expire_items** — Tiered expiry of OPEN nodes past their deadlines:
   - **Hard:** archive at T+0 (immediate)
   - **Soft:** archive at T+48h
   - **Routine:** archive at midnight of deadline day
   - **Undated:** archive after 14 days with no edge updates

### `POST /jobs/nightly-batch` — 3 AM UTC
1. **reset_notifications** — Sets `notification_sent_today = false` on all profiles
2. **detect_patterns** — Per-user pattern analysis:
   - `completion_stats` (db_only): SQL aggregation of completions by day of week
   - `behavioral_patterns` (llm_analysis): GPT analyzes completion + activity data
   - `preference_inference` (llm_analysis): GPT infers tone/length/pushiness from messages
   - Results merged into `user_profiles.patterns` JSONB
3. **nightly_synthesis** — Per-user graph maintenance (see Architecture > Nightly Synthesis)

## Cold Path Dispatch

When a chat completes successfully, the cold path uses **session-level debounce**:

```python
# Store session_id in Redis with 3-min TTL (resets on each message)
await cache_set(f"pending_extraction:{user_id}", session_id, ttl_seconds=180)

# Schedule QStash job — fires when session goes idle
await dispatch_job("process-session", {
    "user_id": user_id,
    "session_id": session_id,
    "trace_id": trace_id,
}, delay=180)

# Intent shift to QUERY → trigger extraction immediately
if query_detected:
    await cache_delete(session_key)
    await dispatch_job("process-session", {...}, delay=0)
```

This hits `POST /jobs/process-session` which:
1. Checks if debounce key still exists (session still active → skip, will be requeued)
2. Calls `process_session()` which loads ALL messages for the session and extracts the NET STATE

The legacy `POST /jobs/process-message` endpoint still exists for backward compat.

## Scheduled Actions

User-facing scheduled reminders/nudges. Created via the proactive system or the `schedule_reminder` agent tool.

### Lifecycle
1. Created with `save_scheduled_action()` — status: `pending`
2. If within 7 days: dispatched precisely via `qstash.dispatch_at()`
3. If >7 days: picked up by hourly safety-net poll
4. On execution: claimed (status: `executing`), dispatched, marked `executed` or `failed`
5. If has rrule: next occurrence calculated, new action created

### Action Types
- `nudge` — Push notification with message
- `reminder` — User-created via `schedule_reminder` tool, dispatched via QStash `dispatch_at()`
- `check_in` — Queued proactive message
- `ask_question` — Queued proactive message
- `surface_item` — Queued proactive message

## Proactive Messaging

### Trigger Evaluation
Runs on `GET /api/messages` initial load (no `before` cursor):

1. Check 6-hour cooldown (from `last_proactive_at`)
2. Load `proactive.yaml` triggers, sorted by priority
3. For each enabled trigger, evaluate condition:
   - `urgent_items` — Queries `vw_actionable` for deadlines within N hours
   - `days_absent` — Compares `last_interaction_at` to now
   - `recent_completions` — Counts `StatusUpdated→DONE` events in last N hours
   - `slipped_items` — Past-due soft deadlines during absence
4. First matching trigger: render prompt template via LLM, save as event
5. Update `last_proactive_at` (cooldown reset)

### Queued Messages
Proactive messages can also be queued in the `proactive_messages` table (by scheduled actions or deadline checks). On initial load, pending queued messages are delivered and marked as such.
