# Known Bugs & Issues

Tracked issues discovered during graph memory integration, production audit, and eval test suite (2026-03-18). Ordered by severity.

Eval baseline: 98 cases, 68 passed (69%), 30 failed — run against `gpt-4o-mini` at commit `b3cfe68`. Full report: `backend/tests/eval/results/20260318_023741_b3cfe68.json`.

---

## Critical (will crash in production)

### BUG-001: `fromisoformat()` crashes on non-ISO deadline strings

**File:** `backend/src/db/supabase.py:153`
**Status:** Partially fixed (string-to-datetime conversion added, but no error handling)

The LLM sometimes returns deadline_at as a non-ISO string (`"tomorrow"`, `"next friday"`, `"end of month"`). `datetime.fromisoformat()` raises `ValueError`, crashing the save_items tool step. The user sees "sorry, something went wrong."

**Fix:** Wrap `fromisoformat()` in try/except, fall back to null deadline with a log warning. Consider adding `dateutil.parser.parse()` as a more lenient fallback.

---

## High (produces wrong results silently)

### BUG-002: Extraction prompt has no current date/time context

**File:** `backend/prompts/brain_dump_extract.md`
**Status:** Open
**Eval evidence:** 2/5 date resolution tests failed. "the presentation is due next Friday" → 0 items saved (deadline couldn't be resolved). "remind me about the meeting in 2 hours" → 0 items saved. "tomorrow" works inconsistently — sometimes resolves, sometimes null.

The extraction prompt tells the LLM to return `deadline_at` as ISO 8601 but never provides the current date or time. When a user says "tomorrow", "this friday", "next week", or "on the 20th", the LLM either:
- Guesses a date from training data (user said "Friday 20th March" in 2026, LLM returned `2024-03-20`)
- Returns the literal string ("tomorrow") which crashes `fromisoformat()`
- Returns null, losing the deadline entirely

The graph ingest prompt already solves this — it passes `current_datetime`. The extraction prompt needs the same.

**Fix:** Inject `current_datetime` into `brain_dump_extract.md` template variables. Add it to `_build_prompt_variables()` in engine.py or pass it from context assembly.

### BUG-003: Extracted datetimes have no timezone

**File:** `backend/src/db/supabase.py:153`, `backend/prompts/brain_dump_extract.md`
**Status:** Open

The LLM returns dates like `"2026-03-20T00:00:00"` (no timezone). `fromisoformat()` creates a naive datetime. PostgreSQL's `TIMESTAMPTZ` column stores it as-is (assumes UTC), but comparisons against `now()` (UTC-aware) may behave inconsistently. The deadline scanner and urgency decay jobs use `now()` comparisons.

**Fix:** After parsing, attach the user's timezone (from profile) or default to UTC. The prompt should instruct the LLM to include timezone offset, or the parsing code should normalize.

### BUG-004: QStash signing keys — EU vs US endpoint mismatch

**File:** `backend/src/auth/qstash_auth.py`
**Status:** Fixed (commit a05601c)

The QStash `Receiver.verify()` was using `str(request.url)` which shows Railway's internal URL (`http://0.0.0.0:8000/...`) instead of the public URL QStash signed against (`https://api.unspool.life/...`). All cron jobs were returning 403.

**Fixed by:** Reconstructing public URL from `API_URL` + `request.url.path`.

---

## Medium (missing functionality)

### BUG-005: No "remind me in X" scheduling mechanism

**Files:** `backend/config/intents.yaml`, pipeline system
**Status:** Open (roadmap item)

Messages like "remind me in 20 minutes", "ping me at 3pm", "tell me about this in 5" have no dedicated intent or pipeline. They get classified as `brain_dump` or `conversation`. Even if an item is created with a deadline, there's no mechanism to actually nudge the user at that time.

The infrastructure exists:
- `nudge_after` column in `items` table (never populated during extraction)
- `QStash.dispatch_at()` function (exists but nothing calls it for user reminders)
- Push notification system (works for deadline scanner)

**Fix:** New `schedule_reminder` intent → pipeline that extracts the time delta, calculates absolute time, sets `nudge_after`, and dispatches a QStash delayed job to a nudge endpoint.

### BUG-006: `nudge_after` field is never set during item extraction

**File:** `backend/prompts/brain_dump_extract.md`, `backend/src/tools/db_tools.py`
**Status:** Open

The `items.nudge_after` column exists in the schema for "don't surface before this time" but is never populated during the extraction pipeline. The `reschedule_item` tool sets it when a user says "skip", but initial extraction ignores it.

**Fix:** Add `nudge_after` to the extraction prompt output schema and pass it through save_items.

### BUG-007: `update_item` doesn't parse datetime fields

**File:** `backend/src/db/supabase.py:265`
**Status:** Open (not currently hit, but fragile)

`update_item(**fields)` passes values directly to asyncpg without type conversion. If a caller ever passes `deadline_at="2026-03-20"` as a string, it would crash. Currently safe because `mark_item_done` and `reschedule_item` don't update `deadline_at`, but the item correction flow (BUG-008) would need this.

**Fix:** Add datetime parsing for known TIMESTAMPTZ fields (`deadline_at`, `nudge_after`, `last_surfaced_at`) in `update_item`.

### BUG-008: Item correction via chat doesn't update deadlines

**Files:** `backend/config/intents.yaml`, pipeline system
**Status:** Open (roadmap item in Phase 2C)

"the meeting moved to Wednesday" or "actually the deadline is next Friday" — the user needs to correct an existing item's deadline. Currently no pipeline handles this. The graph memory system handles corrections (bi-temporal edge invalidation), but the items table correction flow is missing.

---

### BUG-017: Using gpt-4o-mini for everything — no model tiering

**File:** Railway env vars, `backend/src/config.py`
**Status:** Open
**Eval evidence:** Full eval suite run at `b3cfe68` with `gpt-4o-mini` across all pipelines: 69% pass rate overall. Personality/emotional tests: 3/20 passed (15%). The model systematically fails at nuanced prompt-following — it reads "designed for people with ADHD" and defaults to emotional support mode, ignoring negative constraints ("don't assume stress"). Intent classification: 86% (acceptable for fast model). Extraction: 90% (good). The bottleneck is response generation quality, not classification or extraction.

Both `LLM_MODEL` and `LLM_MODEL_FAST` are set to `gpt-4o-mini`. This is a cheap/fast model that's weak at:
- Date resolution ("Friday 20th March" → returned 2024 instead of 2026)
- Following nuanced prompt instructions (adds unsolicited empathy, ignores "don't assume stress")
- Complex extraction (misses implicit items, wrong urgency estimates)

Need to evaluate and tier models by task:

| Task | Current | Needs | Candidates |
|------|---------|-------|------------|
| Intent classification | gpt-4o-mini | Fast + accurate | gpt-4.1-nano, gpt-4.1-mini |
| Item extraction | gpt-4o-mini | Good structured output + date resolution | gpt-4.1-mini, claude-haiku-4-5 |
| Response generation | gpt-4o-mini | Natural tone, follows personality rules | gpt-4.1, claude-sonnet-4-5 |
| Graph ingest | gpt-4.1-nano | Fast structured JSON (current is fine) | gpt-4.1-nano |
| Graph feedback | gpt-4.1-nano | Fast structured JSON (current is fine) | gpt-4.1-nano |
| Graph evolution | gpt-4.1-nano | Needs reasoning for merges/contradictions | gpt-4.1-mini |

**Fix:** Benchmark each task with candidate models on golden test cases (Phase 2B). Set per-step model overrides in pipeline YAMLs (already supported via `model:` field). Use `LLM_MODEL` for response generation (quality matters) and `LLM_MODEL_FAST` for classification/extraction (speed matters).

### BUG-018: System prompt causes unsolicited empathy in every response

**File:** `backend/prompts/system.md`
**Status:** Open
**Eval evidence:** 10/12 personality tests failed, 7/8 emotional calibration tests failed, 3/12 regression tests failed — all due to empathy projection. This is the single highest-impact bug in the system.

The system prompt says "designed for people with ADHD" (line 6) and "match the user's energy — if they're stressed, acknowledge it before problem-solving" (line 13). This is injected into every LLM call. The LLM reads this and assumes the user is overwhelmed/stuck/struggling, adding phrases like "that feels overwhelming" or "you're stuck" to neutral messages like "I have an exam Friday."

The personality section primes the LLM for emotional support mode even when the user is just listing tasks matter-of-factly.

**Eval responses demonstrating the bug:**
- "I need to buy milk and eggs" → "It sounds like you've got a little shopping to do. Hope you can make it out to grab those soon!" (projected concern)
- "laundry, dishes, vacuum" → "It sounds like you've got a few things on your mind! Just take it one step at a time; tackling even one of those tasks can help lighten the load a bit." (projected overwhelm, motivational language)
- "I have an exam Friday" → "Gotcha! Sounds like you've got a big day coming up on Friday. How are you feeling about it?" (probed for stress, asked an unnecessary question)
- "pick up prescription" → "Sounds like you've got a prescription to grab! It can be a bit of a hassle, but you've got this." (projected difficulty, cheerleading)
- "morning. need to send that email and prep for the meeting" → "Good morning! Sounds like you've got a couple of important things on your plate today. Just take it one step at a time, and you'll get through it!" (projected struggle, motivational closing)

The pattern is consistent: gpt-4o-mini reads "designed for people with ADHD" + "match the user's energy" and defaults to emotional support mode regardless of the user's actual tone. Neutral, matter-of-fact inputs consistently get empathetic, slightly patronizing responses.

**Fix:** Three changes to `system.md`:
1. Remove "designed for people with ADHD" from line 6. The product IS for ADHD but telling the LLM that makes it patronizing.
2. Replace "match the user's energy — if they're stressed, acknowledge it before problem-solving" (line 13) with: "Match the user's tone. If they're matter-of-fact, be matter-of-fact. If they express stress, acknowledge it. Don't assume emotions that aren't expressed."
3. Add explicit negative constraint: "Never assume the user is stressed, overwhelmed, or struggling unless they explicitly say so. Never add motivational phrases like 'you've got this', 'you can do it', 'one step at a time'. Just acknowledge what they said."

Also fix `brain_dump_respond.md` line 14: "If they mentioned feelings or stress alongside tasks, acknowledge the feeling first" — this line triggers empathy even when no feelings were mentioned. Change to: "If the user explicitly expressed feelings or stress (not inferred), acknowledge the feeling first."

---

### BUG-019: query_next returns multiple suggestions instead of one

**File:** `backend/prompts/query_format.md`, `backend/prompts/system.md`
**Status:** Open (discovered by eval)
**Eval evidence:** personality_no_list test: user asked "what should I do?" with 5 open items in context. Response: "How about tackling your Q1 quarterly report? You've got the energy for it, and getting that out of the way will feel like a big weight lifted off your shoulders! Plus, you'll be one step closer to mee..." — judge scored 1/10 for single_item because the response suggests multiple actions and adds commentary about "one step closer" implying there are more things to do.

The system prompt says "When asked 'what should I do?' — give ONE thing, never a list" (line 16) but gpt-4o-mini doesn't follow this consistently. The model adds qualifiers and context that imply other items exist, breaking the "no accumulation" design principle.

The `query_format.md` prompt says "Present exactly ONE thing to do, never a list" but doesn't explicitly forbid mentioning other items or progress toward a larger set.

**Fix:** Add to `query_format.md`: "Never mention how many items remain, never say 'one down', 'one step closer', or imply there's a backlog. The user should feel like this is the only thing that matters right now."

### BUG-020: Energy estimate extraction defaults to "medium" for obviously low-energy tasks

**File:** `backend/prompts/brain_dump_extract.md`
**Status:** Open (discovered by eval)
**Eval evidence:** extract_low_energy test: user said "I need to text my mom back" → item saved with `energy_estimate: "medium"` instead of `"low"`. Texting someone back is a <1 minute, zero-effort task — "low" is clearly correct.

The extraction prompt relies on the LLM to infer energy_estimate, and the `enrich_items` tool only fills defaults when the LLM returns null. The LLM (gpt-4o-mini) has a bias toward "medium" as a safe default, underestimating how low-effort some tasks are.

**Fix:** Add examples to the extraction prompt showing the energy scale: "low = under 5 minutes, no preparation needed (text someone, quick call, check email). medium = 15-60 minutes or requires some focus (write a short email, review a document). high = 1+ hours or requires deep focus (write a report, study for exam, build something)."

### BUG-021: Intent classification confuses related intents on ambiguous inputs

**File:** `backend/prompts/classify_intent.md`
**Status:** Open (discovered by eval)
**Eval evidence:** 5/35 intent classifications wrong (85.7% accuracy). Failure patterns:

| Input | Expected | Got | Analysis |
|-------|----------|-----|----------|
| "when is that meeting with Jake?" | query_search | query_upcoming | "when" triggers temporal → upcoming, but the user is searching for a specific item |
| "I actually got so much done today! feeling great" | emotional | status_done | "got so much done" triggers completion language |
| "what can you do?" | meta | onboarding | Both ask about capabilities; LLM can't distinguish returning user from new user without conversation history |
| "hi" | onboarding | conversation | Bare greeting without context; LLM defaults to conversation |
| "just got back from the store" | status_done | conversation | Implicit completion; no explicit "done" marker |

The classify_intent prompt lists intents but doesn't provide disambiguation rules for overlapping cases. The LLM picks the most salient keyword match rather than considering the full intent taxonomy.

**Fix:** Add disambiguation hints to `classify_intent.md`:
- "query_search vs query_upcoming: If the user references a *specific* item/person/event, it's query_search. If they ask about a time range or 'what's coming up', it's query_upcoming."
- "emotional vs status_done: If the user expresses a *feeling* (even positive), it's emotional. 'I got so much done' with an exclamation is celebrating, not reporting completion."
- "meta vs onboarding: If the user has recent conversation history, it's meta. If no recent messages exist, it's onboarding."
- "onboarding vs conversation: A bare 'hi' or 'hello' from a user with no recent messages is onboarding. With recent messages, it's conversation."
- "status_done vs conversation: status_done requires the user to reference a *specific task* they completed. General statements about activities ('just got back from the store') are conversation unless they match a known item."

### BUG-022: Emotional calibration — responses don't scale with detected level

**File:** `backend/prompts/emotional_respond.md`
**Status:** Open (discovered by eval)
**Eval evidence:** 7/8 emotional detection tests failed. The emotional_respond prompt defines clear guidelines per level (LOW/MEDIUM/HIGH) but the LLM doesn't follow them:

| Input | Expected behavior | Actual response | Score |
|-------|-------------------|-----------------|-------|
| "I'm freaking out, deadline in 2 hours" (HIGH) | Pure support, zero tasks | "That sounds really hard. The pressure can feel overwhelming..." — lectured about pressure | calm: 4, no_lecture: 2 |
| "ugh I keep putting off the taxes" (MEDIUM) | Validate + practical help | Pipeline crashed (eval framework bug) | 1 |
| "I'm so tired today, brain isn't working" (MEDIUM) | Adjust expectations, suggest rest | "It's okay to have days like this" — patronizing | validate: 6 |
| "need to finish slides before Thursday" (LOW) | Match matter-of-fact tone | "Let's tackle those slides together... You've got this!" — cheerleading | tone: 4, support: 3 |
| "pick up the dry cleaning" (LOW) | Simple acknowledge | "It sounds like you're thinking about picking up the dry cleaning... if you're feeling overwhelmed..." — massively over-empathized | simple: 3, brevity: 3 |
| "I finished everything today!" (POSITIVE) | Brief shared joy | Pipeline crashed (eval framework bug) | 1 |

Two problems:
1. The emotional detect step classifies the level, but the respond step doesn't reliably follow the level-specific rules. The system prompt's "designed for people with ADHD" (BUG-018) overrides the emotional_respond prompt's level guidance.
2. LOW emotional responses get the same empathetic treatment as HIGH, violating the "match the user's tone" principle.

**Fix:** This is mostly BUG-018 — fixing the system prompt will likely fix most of these. Additionally, the emotional_respond prompt should make the LOW rules more explicit: "For LOW: Your response should be indistinguishable from a normal brain_dump response. No emotional language. No validation. Just acknowledge what they said. The word 'feel' should not appear in a LOW response."

### BUG-023: Motivational/cheerleader language in every response

**File:** `backend/prompts/system.md`, `backend/prompts/brain_dump_respond.md`
**Status:** Open (discovered by eval)
**Eval evidence:** Phrases like "you've got this!", "you'll be making progress in no time", "one step at a time", "you can do it", "let's tackle this together" appear across nearly all failed personality tests. These phrases violate the product's "quiet respect" principle.

The system prompt says "celebrate small wins without being patronizing" (line 12) and "warm, casual, and genuinely caring" (line 9). gpt-4o-mini interprets "genuinely caring" + "celebrate" as a mandate to add motivational closings to every response.

**Eval responses showing the pattern:**
- "what's next?" → "...you'll be making progress in no time" (cheerleading score: 3/10)
- "need to finish slides before Thursday" → "...You've got this!" (unsolicited support score: 3/10)
- "I keep forgetting to do things" → "...we can figure out a little trick to help you remember" (implied diagnosis score: 3/10)
- "add dentist appointment" → "...it's super important for keeping your smile bright. If you need to talk about it, I'm here for you!" (projected difficulty score: 5/10)

**Fix:** Add to `system.md`: "Never end a response with motivational phrases like 'you've got this', 'you can do it', 'one step at a time', 'let's tackle this'. These feel performative. Just say what needs saying, then stop." Also remove "celebrate small wins" — the user's positive moments should be acknowledged briefly, not celebrated. Replace with: "If the user shares good news, acknowledge it briefly. Don't cheer."

### BUG-024: brain_dump_respond prompt triggers questions and elaboration

**File:** `backend/prompts/brain_dump_respond.md`
**Status:** Open (discovered by eval)
**Eval evidence:** personality_brevity test: "I need to buy groceries" → "Got it! Grocery shopping can feel like a lot sometimes. Do you want to pick one thing to focus on first?" — asks a question (violates zero-decisions principle) and adds commentary about groceries "feeling like a lot" (unsolicited empathy). Judge scored brevity 5/10.

personality_no_questions test: "pick up prescription" → "Sounds like you've got a prescription to grab! It can be a bit of a hassle, but you've got this." — adds difficulty projection ("hassle") and cheerleading ("you've got this"). Judge scored zero_decisions 3/10.

The brain_dump_respond prompt says "Make them feel heard, not processed" (line 15) which the LLM interprets as needing to add conversational filler. Combined with BUG-018's system prompt priming, every acknowledgment becomes an empathy performance.

**Fix:** Replace "Make them feel heard, not processed" with "Confirm you captured it. That's all." Add: "Never ask follow-up questions. Never elaborate on the task. Never add commentary about how the task might feel. Just confirm and stop. Examples of good responses: 'got it.', 'noted — groceries and dentist.', 'on it.'"

---

## Low (cosmetic or edge cases)

### BUG-009: `save_item` `$5::timestamptz` SQL cast is now redundant

**File:** `backend/src/db/supabase.py:154`
**Status:** Open (harmless)

After the fix to parse `deadline_at` to a datetime object, the `$5::timestamptz` SQL cast is redundant (asyncpg already sends the correct type). Removing it would be cleaner but isn't a bug.

### BUG-010: Calendar event timestamps use `::timestamptz` cast

**File:** `backend/src/db/supabase.py:783`
**Status:** Open (currently safe)

`upsert_calendar_events` uses `$4::timestamptz` and `$5::timestamptz` casts. These work because Google Calendar API returns proper datetime objects. But if the code ever receives string dates, the same crash would occur. Low risk since the data source is controlled.

### BUG-011: Subscription `current_period_end` uses `::timestamptz` cast

**File:** `backend/src/db/supabase.py:1085`
**Status:** Open (currently safe)

Same pattern as BUG-010. Stripe API returns integer timestamps that are converted upstream. Low risk.

---

### BUG-014: query_next prompt ignores conversation history when items table is empty

**Files:** `backend/prompts/query_format.md`, `backend/config/pipelines/query_next.yaml`
**Status:** Open
**Eval evidence:** multi_correction test: user said "the meeting is on Thursday", then corrected to "actually the meeting moved to Friday", then asked "what's coming up?" → response: "It looks like there's nothing on the horizon right now, so you can just chill" (score 1/10). The correction flow doesn't persist items, so query_upcoming sees nothing and tells the user their plate is clear — even though the conversation just discussed a meeting on Friday.

When `pick_next_item` returns None (no items in DB), the prompt tells the LLM "No items found — the user's plate is clear." The LLM obediently says "you're all clear!" even if the user just listed 5 tasks in the conversation seconds ago.

The recent conversation IS in the LLM's message history (injected by `engine.py`), but the explicit prompt instruction "user's plate is clear" overrides it. The LLM follows the prompt over the conversation context.

This is especially bad when combined with BUG-001 (save_items crash) — items fail to save silently, then the user asks what to do and gets told there's nothing.

**Fix:** The `{% else %}` branch in `query_format.md` should tell the LLM to check conversation history: "No items in the database. Check the recent conversation — the user may have mentioned things that weren't saved. If you can see things they mentioned, suggest one. Otherwise, say they're all clear."

Also: pass `recent_messages` as an explicit input to the respond step so the prompt can reference it directly.

### BUG-015: Silent item save failures — user thinks items were saved

**Files:** `backend/src/orchestrator/engine.py`, `backend/src/api/chat.py`
**Status:** Open

When `save_items` crashes (e.g. BUG-001 deadline_at parse error), the pipeline still generates a response using the in-memory extracted items. The user sees a normal "got it, I'll remember that" response but the items were never persisted. Next time they ask "what should I do?", `fetch_items` returns nothing and the AI says there's nothing to do.

The user has no way to know the save failed. The error is logged in Langfuse as a tool_step ERROR but the pipeline continues to the respond step.

**Fix:** The `save_items` tool step should propagate the error so the respond step knows items weren't saved. Or: the respond prompt should receive a `saved_count` variable and adjust its response ("I tried to save that but something went wrong").

### BUG-015: `assemble_context` slow when graph_context is optional

**File:** `backend/src/tools/graph_tools.py`, `backend/config/context_rules.yaml`
**Status:** Open

Adding `graph_context` as optional to intents (query_next, brain_dump, etc.) causes `fetch_graph_context` to run on every message. Even with an empty graph, this fires an OpenAI embedding API call (~1-2s latency) before discovering there's nothing to retrieve. Observed: `assemble_context` taking 6.1s for a simple query_next.

**Fix:** `fetch_graph_context` should check if the graph has any nodes BEFORE calling the embedding API. The `get_graph_stats()` check already exists (line 28-29) but runs after the imports. Move the empty-graph check before the embedding call. Also consider: only load graph_context for intents where it adds value (query_next yes, onboarding no).

### BUG-016: `graph_context` embedding call happens even when graph is empty

**File:** `backend/src/tools/graph_tools.py:38-43`
**Status:** Open

`fetch_graph_context` checks `stats.get("nodes", 0) == 0` and returns None early. But this check happens before the embedding call (line 39-43) only if the graph stats query succeeds. The embedding call should be AFTER the stats check, not before. Currently the code is ordered correctly (stats check at line 28, embedding at line 39), but the stats check queries a DB table that may be slow on first call.

Actually on re-read, the order is correct: stats → return None if empty → embed. But the 6.1s suggests something else is slow in context assembly, likely the parallel loading of all context fields including graph_context's DB round-trip.

---

### BUG-025: Pipeline crashes silently on status_done/status_cant — user sees generic error

**Files:** `backend/src/tools/item_matching.py`, `backend/config/pipelines/status_done.yaml`
**Status:** Open (discovered by eval — 5 pipeline crashes observed)
**Eval evidence:** When `status_done` or `status_cant` pipelines run, the `match_item` tool step calls `fuzzy_match_item` which calls `db.get_open_items()` and `db.search_items_text()`. If either DB call fails, the entire pipeline crashes and the user sees "sorry, something went wrong on my end." The crash propagates through the pipeline's tool_call step, which doesn't have retry or graceful degradation for the matching step.

Also observed: `emotional` pipeline crash when the `emotional_detect` step fails — user sees generic error instead of any emotional support.

In the eval, 5/98 cases crashed (personality_acknowledge_done, emotion_medium_frustrated, emotion_positive_celebration, perf_status_done, perf_status_cant). In production this would mean ~5% of user messages that hit these pipelines get a "something went wrong" response.

**Fix:** The `match_item` tool step should fail gracefully — if item matching fails, the pipeline should continue to the respond step with a null match, and the respond prompt should handle that case ("I couldn't find that one — can you be more specific?"). Currently the pipeline YAML has no `retry` or fallback for tool_call steps.

---

## Pre-existing (not from graph integration)

### BUG-012: QStash token in local env file is stale

**File:** `env` (local, not committed)
**Status:** Open

The local env file has the old QStash token (without trailing `=`) and uses the US endpoint URL. Railway has the correct values. The local env file needs updating for local development.

### BUG-013: All QStash cron jobs were silently failing

**Status:** Fixed (commit a05601c — QStash URL fix)

Every cron job (check-deadlines, decay-urgency, sync-calendar, detect-patterns, reset-notifications) was returning 403 due to signature verification mismatch. This means:
- No deadline push notifications were being sent
- No urgency decay was running (items never expired)
- No calendar sync was happening
- No pattern detection was running
- Notification-sent-today flag was never reset

All fixed now that signature verification uses the public URL.
