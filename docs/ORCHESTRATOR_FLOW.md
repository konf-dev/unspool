# Orchestrator Flow — Complete System Architecture

**This document defines every path through the system, from user message to response.**

---

## High-Level Flow

```
User Message
    │
    ▼
┌─────────────┐
│  GATE LAYER  │ ── Auth, rate limit, session load
└──────┬──────┘
       │
       ▼
┌──────────────┐
│   CONTEXT    │ ── Load user profile, recent items, conversation history
│   ASSEMBLY   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    INTENT    │ ── What is the user trying to do?
│  CLASSIFIER  │
└──────┬───────┘
       │
       ├──► BRAIN DUMP ──────────────► Item Extraction Pipeline
       ├──► QUERY ───────────────────► Query Resolution Pipeline
       ├──► STATUS UPDATE ───────────► State Mutation Pipeline
       ├──► EMOTIONAL SIGNAL ────────► Emotional Adjustment Pipeline
       ├──► META / SYSTEM ───────────► System Action Pipeline
       ├──► FIRST OPEN / ONBOARDING ► Onboarding Pipeline
       ├──► CONVERSATION ────────────► Conversational Pipeline
       │
       ▼
┌──────────────────┐
│ PERSONALIZATION  │ ── Adjust tone, length, style to user's patterns
│     LAYER        │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│    RESPONSE      │ ── Format and deliver
│    DELIVERY      │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   POST-PROCESS   │ ── Embeddings, entity extraction, memory extraction
│                  │    (dispatched via QStash after response saved)
└──────────────────┘

Error handling:
  ├── Pipeline crash → user sees "sorry, something went wrong"
  ├── Timeout (60s) → user sees "sorry, that took too long"
  ├── LLM API down → falls back to conversation intent
  └── Redis down → rate limiting skipped (fail open)
```

---

## 0. Gate Layer

Every message hits this first. No LLM calls — pure logic.

```
User Message
    │
    ▼
Is user authenticated?
    ├── NO → Is this first visit?
    │         ├── YES → Create session → ONBOARDING
    │         └── NO  → Show magic link / login
    │
    ├── YES → Check rate limit
    │         ├── OVER LIMIT (free tier, 10 msgs/day)
    │         │     → "I'm out of messages for today.
    │         │        Unlimited is $8/month — want me to set that up?"
    │         │     → Wait for yes/no (doesn't count against limit)
    │         │
    │         └── UNDER LIMIT → Load session → CONTEXT ASSEMBLY
    │
    ▼
Proceed
```

**Notes:**
- Rate limit is the ONLY place free/paid distinction exists in the system
- Upgrade prompt is IN the chat, not a modal or redirect
- "Yes" to upgrade → Stripe checkout link inline
- First-time detection happens here, not in intent classifier

---

## 1. Context Assembly

Before the intent classifier runs, assemble what it needs. NOT an LLM call — database queries.

```
Load:
  ├── User profile (name, inferred patterns, personalization prefs)
  ├── Last N messages in conversation (for continuity)
  ├── Open items summary (count, nearest deadlines, oldest items)
  ├── Any items with hard deadlines in next 48h (pre-fetched)
  └── Time since last interaction (used for re-entry behavior)

Output: context_bundle (passed to all downstream pipelines)
```

**Retrieval rules (token/cost management):**
- If user has < 20 items total → load all as context
- If user has > 20 items → load: all hard-deadline items + top 10 by urgency + items mentioned in last 5 messages
- Always load user profile and last 5 messages
- Never load done/expired items unless user explicitly asks about history

---

## 2. Intent Classifier

Takes user message + context_bundle, returns an intent.

```
Intents:
  BRAIN_DUMP      — user is dumping stuff
  QUERY_NEXT      — "what should I do?"
  QUERY_UPCOMING  — "what's coming up?"
  QUERY_SEARCH    — "did I ever think about X?"
  QUERY_OVERVIEW  — "what's on my plate?" (v0.2)
  STATUS_DONE     — "done with X"
  STATUS_CANT     — "can't do this" / "skip"
  EMOTIONAL       — "bad day" / "overwhelmed"
  META_UPGRADE    — wants to upgrade/downgrade
  META_CANCEL     — wants to cancel subscription
  META_HELP       — "how does this work?"
  META_DELETE     — "forget about X" / "remove"
  ONBOARDING      — first interaction ever
  CONVERSATION    — just chatting, not a command
  MIXED           — multiple intents in one message
```

**Rule-based fast path (no LLM needed):**
- Starts with "done" / "finished" / "completed" → STATUS_DONE
- "what should I do" / "what now" / "help me pick" → QUERY_NEXT
- "bad day" / "overwhelmed" / "can't today" → EMOTIONAL
- "cancel" / "unsubscribe" → META_CANCEL
- First ever message from user → ONBOARDING

**v0.1 note:** Intent classification is LLM-only — the rule-based fast path described above is not implemented. All messages go through the `classify_intent` prompt. This avoids misclassification on ambiguous inputs at the cost of one extra LLM call.

**LLM needed for:**
- "I emailed my supervisor and also need to book flights next week" → MIXED
- "The standup went well but I'm worried about the thesis deadline" → MIXED
- Anything ambiguous

**MIXED intent handling:**
- Split into sub-intents
- Process each through its pipeline
- Merge responses

---

## 3. Pipelines

### 3A. BRAIN DUMP Pipeline

```
User message
    │
    ▼
┌────────────────────┐
│  ITEM EXTRACTION   │ ── LLM call
│                    │    Extract individual items from message
│                    │
│  "email supervisor │    → [ "email supervisor about ch3",
│   about ch3, buy   │       "buy laundry detergent",
│   laundry stuff,   │       "idea: RL for fleet optimization" ]
│   had an idea      │
│   about RL for     │
│   fleet stuff"     │
└────────┬───────────┘
         │
         ▼ (for each item)
┌────────────────────┐
│  ITEM ENRICHMENT   │ ── LLM or rule-based per item
│                    │
│  For each item:    │
│   ├── Interpreted action (clean description)
│   ├── Item type: task / event / idea / context
│   ├── Deadline type: hard / soft / none
│   ├── Deadline value: inferred date or null
│   ├── Energy estimate: low / medium / high
│   ├── Initial urgency score: 0-1
│   └── Duplicate check: does this already exist?
│                    │
└────────┬───────────┘
         │
         ├── Duplicate found → Update existing item
         ├── New item → Store in database
         │
         ▼
┌────────────────────┐
│   GENERATE ACK     │ ── LLM call: short confirmation
│                    │
│  Rules:            │
│   - One line per item, max 2-3 lines total
│   - Mention inferred deadline if any
│   - No categories shown
│   - No priority shown
│   - No follow-up questions unless critically ambiguous
│                    │
│  Example:          │
│  "got it — nudge you about the supervisor email
│   in a couple days. flights noted for next week.
│   saved the RL idea."
└────────┬───────────┘
         │
         ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

**Deduplication logic:**
- "need to email supervisor" when "email supervisor about chapter 3" exists → update existing, don't create duplicate
- Fuzzy matching needed — "email prof" and "email supervisor" might match if context shows they're the same person
- When in doubt, store as new (false negatives worse than duplicates)

---

### 3B. QUERY Pipelines

#### QUERY_NEXT — "What should I do?"

```
context_bundle
    │
    ▼
┌──────────────────────┐
│   URGENCY SCORING    │ ── Code, not LLM
│                      │
│  Score = f(          │
│    deadline_proximity,│  How close to blowing up?
│    deadline_hardness, │  Hard external vs soft?
│    age,              │  How long sitting?
│    times_surfaced,   │  Already nagged about this?
│    energy_fit        │  Match to current user energy?
│  )                   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  INFER USER ENERGY   │ ── Code, not LLM
│                      │
│  Just dumped 10 items        → LOW (overwhelmed)
│  Proactively asked for task  → MEDIUM-HIGH
│  Said "done" 3x in a row    → HIGH (in flow)
│  First msg after long silence→ MEDIUM (default)
│  Said "bad day" recently     → LOW
│                      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    PICK ONE ITEM     │
│                      │
│  Energy HIGH → highest urgency regardless
│  Energy LOW  → highest urgency that is LOW energy
│               (quick win to build momentum)
│  Energy MED  → highest urgency that isn't HIGH energy
│                      │
│  Anti-nag: if item was surfaced last 2 interactions,
│  skip to next (unless hard deadline today)
│                      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  FORMAT RESPONSE     │ ── LLM call
│                      │
│  ONE item. Why now.  │
│  Maybe a first step  │
│  (only if high energy│
│   and high-effort    │
│   task)              │
│                      │
│  "the supervisor email — it's been 4 days
│   and it's a quick one."
└──────────┬───────────┘
           │
           ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

#### QUERY_UPCOMING — "What's coming up?"

```
DB query: open items where deadline_at <= now + 48h
    │
    ├── 0 items → "nothing urgent in the next couple days."
    ├── 1-3 items → list naturally in a sentence
    ├── 4+ items → summarize: "4 things before Thursday.
    │               Big ones: rent and thesis draft."
    ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

#### QUERY_SEARCH — "Did I ever mention X?"

```
User message
    │
    ▼
┌────────────────────┐
│  ANALYZE QUERY     │ ── LLM call (analyze_query.md)
│                    │    Determines: search_type, entity,
│                    │    timeframe, which sources to query,
│                    │    text search terms, status filter
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  SMART FETCH       │ ── Tool call (smart_fetch)
│                    │    Resolves entity names → IDs
│                    │    Constructs targeted DB queries
│                    │    Searches: items, memories,
│                    │    messages, calendar (as needed)
└────────┬───────────┘
         │
         ├── 0 results → "I don't have anything about that."
         ├── Found → "yeah, about 3 weeks ago you mentioned
         │            transformer attention for scheduling.
         │            want me to pull up the details?"
         ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

#### QUERY_OVERVIEW — "What's on my plate?"

> **Note:** QUERY_OVERVIEW is planned for v0.2. Not implemented in v0.1.

```
NOT a full list. A narrative summary:
    │
    ▼
  1. Anything on fire (hard deadlines within 48h)
  2. Total count (number only, no list)
  3. What's been sitting longest
  4. General vibe ("pretty manageable" / "a lot right now")

  "rent's due in 2 days — that's the only urgent one.
   you've got about 12 things open, mostly small stuff.
   the thesis chapter has been sitting for a while."
    │
    ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

---

### 3C. STATUS UPDATE Pipelines

#### STATUS_DONE — "Done with X"

```
User message
    │
    ▼
┌──────────────────────┐
│   ITEM MATCHING      │
│                      │
│  Exact match on interpreted_action
│  OR fuzzy/semantic match
│  OR ambiguous → ask: "which one — the supervisor
│                  email or the PhD application?"
│  OR no match → "I don't have that tracked, but nice!"
└──────────┬───────────┘
           │
           ▼
  Mark item status = done
  Record completion timestamp
           │
           ▼
┌──────────────────────┐
│  MOMENTUM CHECK      │
│                      │
│  1st done this session → "nice."
│  2nd done → "on a roll."
│  3rd+ done → "crushing it. want the next one?"
│                      │
│  Keep brief. No fake celebrations.
└──────────┬───────────┘
           │
           ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

#### STATUS_CANT — "Skip" / "Not now"

```
Identify which item (last surfaced, or named)
    │
    ▼
  Reschedule:
    Hard deadline → push nudge by few hours only
    Soft deadline → push nudge by 2 days
    No deadline → push nudge by 1 week
    │
  Lower urgency_score slightly
    │
  NEVER guilt. "no worries, I'll bring it back later"
    │
  Optionally offer the next item
    │
    ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

---

### 3D. EMOTIONAL SIGNAL Pipeline

```
Detect emotional level:
    │
    ├── CRISIS (concerning language)
    │     → Do NOT engage as productivity tool
    │     → Be caring. Suggest real support.
    │     → Do NOT suggest tasks.
    │
    ├── VENTING (needs to talk, not be managed)
    │     → Acknowledge. Don't problem-solve.
    │     → "that sounds really frustrating."
    │
    ├── OVERWHELMED (paralyzed by volume)
    │     → MASS DEPRIORITIZE: push all soft deadlines by 2 days
    │     → "I pushed everything that can wait.
    │        only [N] things actually need you soon."
    │     → If N = 0: "nothing needs you right now. rest."
    │
    ├── LOW_ENERGY (tired, bad day)
    │     → Set session energy flag = LOW
    │     → "rough one. I'm here if you need me."
    │     → Future QUERY_NEXT calls → only LOW energy items
    │
    ├── FRUSTRATED (tried and failed)
    │     → Acknowledge frustration
    │     → Offer to break stuck item into smaller steps
    │     → "want me to break that down into smaller pieces?"
    │
    ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

---

### 3E. META / SYSTEM Pipeline

```
META_HELP     → "just tell me what's on your mind. I'll remember it
                 and nudge you when it matters." (2-3 lines, no feature list)

META_UPGRADE  → Stripe checkout link inline. One tap.

META_CANCEL   → Confirm once: "your items stay, just loses unlimited.
                 sure?" → YES → cancel via Stripe API

META_DELETE   → "forget about the dentist thing"
                → Find item, mark deleted → "gone."

META_FEEDBACK → "this response was bad" → Log for improvement. Acknowledge.

META_EXPORT   → (future) export all items as text/JSON
```

---

### 3F. ONBOARDING Pipeline

```
First ever message
    │
    ├── User started with a brain dump
    │     → Process as BRAIN_DUMP
    │     → Append: "welcome — I'll keep track of that.
    │                just keep telling me stuff."
    │
    ├── User started with greeting ("hi")
    │     → "hey. tell me what's on your mind —
    │        tasks, deadlines, random thoughts, whatever.
    │        I'll keep track."
    │
    NO feature tour. NO setup questions.
    NO "what's your name?" (learn from context later).
    The onboarding IS using the product.
```

---

### 3G. CONVERSATION Pipeline

```
Message is conversational, not a command
    │
    ▼
  Check: is there IMPLICIT info here?
    │
    ├── "yeah the meeting went okay"
    │     → Contains context. Store if relevant.
    │
    ├── "thanks"
    │     → Pure social. "anytime."
    │
    ├── "hmm not sure about that"
    │     → Refers to previous turn. Re-engage.
    │
  Extract implicit items/context if any.
  Keep response conversational.
  Don't turn every message into a productivity moment.
    │
    ▼
   → PERSONALIZATION → RESPONSE DELIVERY
```

---

## 4. Personalization Layer

Runs AFTER every pipeline, BEFORE response delivery.

```
What it adjusts:

TONE (inferred from user's writing style)
  casual    → user uses "lol", "haha", slang
  neutral   → user writes plainly
  warm      → user uses "thanks!", expressive language

LENGTH
  terse     → user sends short messages → reply short
  medium    → default
  detailed  → user asks follow-ups → preempt with detail

PUSHINESS
  gentle    → default. "this is still here if you want to get to it"
  moderate  → "you should probably get to this"
  firm      → "you really need to do this today"
  (adjusted by explicit request: "be more pushy with me")

EMOJI
  Mirror user. Never uses → none. Frequently uses → light use.

LANGUAGE
  Match automatically. Swedish in → Swedish out. No config.

User profile fields (updated over time):
  tone_preference: casual / neutral / warm
  length_preference: terse / medium / detailed
  pushiness_preference: gentle / moderate / firm
  uses_emoji: boolean
  primary_language: string
  avg_message_length: int
  explicit_prefs: [] (things user explicitly asked for)
```

---

## 5. Post-Processing (After Response Sent)

Runs asynchronously. User doesn't wait for this.

```
├── Update last_surfaced_at on any items shown
│
├── Update user profile with interaction data
│
├── Recalculate urgency_score for all open items:
│     Closer to deadline → score UP
│     Untouched for a while → score slowly DECAYS (not accumulates!)
│     User skipped → score drops slightly
│
├── Schedule push notification if needed:
│     Hard deadline in next 24h? + No notification sent today?
│     → Schedule ONE notification consolidating all urgent items
│
├── Expire old items:
│     Soft deadline passed > 7 days ago, never completed → expired
│     No deadline, not surfaced in 30 days → expired
│     (Expired = invisible but NOT deleted, still searchable)
│
├── Dispatch process_graph job (5s delay):
│     Extract nodes/edges from user message → graph memory
│     Generate embeddings for new nodes
│     Detect surfaced/completed items from assistant response
│
└── Log interaction (intent, items affected, response length)
      NOT raw message content in analytics — that's private
```

---

## 6. Background Jobs (Cron, Not User-Triggered)

All background jobs are FastAPI endpoints on the same server, called by Upstash QStash on a schedule. No separate worker process.

```
Job: DEADLINE SCANNER
Endpoint: POST /jobs/check-deadlines
Schedule: Every hour (QStash cron)
  For each user:
    Hard deadlines in next 24h?
      YES + no notification today → send ONE push notification
      (consolidate all urgent items into one message)
      NO → do nothing
  Quiet hours: suppress 1am-7am user local time

Job: URGENCY DECAY/GROWTH
Endpoint: POST /jobs/decay-urgency
Schedule: Every 6 hours (QStash cron)
  Hard deadline items: urgency INCREASES as deadline approaches
  Soft deadline items past window: urgency slowly DECAYS (*= 0.95)
  No-deadline items older than 30 days + score < 0.1: auto-expire
  (expired = invisible, not deleted, still searchable)

Job: POST-CONVERSATION PROCESSING
Endpoint: POST /jobs/process-conversation
Trigger: QStash delayed message, enqueued after each chat (5-10s delay)
  1. Duplicate/merge check on newly created items
  2. Generate embeddings for new items → store in pgvector
  3. Extract user profile facts from conversation → SEMANTIC tier
  4. Re-scan for silently extracted items from CONVERSATION intents

Job: CALENDAR SYNC
Endpoint: POST /jobs/sync-calendar
Schedule: Every 4 hours (QStash cron)
  For each user with Google Calendar connected:
    Fetch next 7 days of events via Google Calendar API
    Store/update in SEMANTIC tier as calendar_event items
    Delete events that no longer exist
    If OAuth token expired: refresh or mark disconnected

Job: PATTERN DETECTION
Endpoint: POST /jobs/detect-patterns
Schedule: Once daily (QStash cron)
Config: config/patterns.yaml defines which analyses run
  For each active user (last 30 days):
    1. completion_stats (db_only) — completions by day of week, averages
    2. behavioral_patterns (LLM) — productivity timing, avoidance, energy cycles
    3. preference_inference (LLM) — tone, length, pushiness, emoji, language
  Store insights in user_profiles.patterns JSONB field
  Respects min_data_days and confidence_threshold per analysis

Job: GRAPH MEMORY PROCESSING
Endpoint: POST /jobs/process-graph
Trigger: QStash delayed message, enqueued after brain_dump/status_done/
         conversation/emotional pipelines (5s delay)
  1. Pre-filter: skip trivial messages (<3 chars, emoji-only)
  2. LLM extracts nodes/edges/corrections from user message
  3. Generate halfvec embeddings for new nodes
  4. Detect which nodes the response surfaced/completed
  5. Create status edges (surfaced, done) + invalidate "not done" edges

Job: NOTIFICATION RESET
Endpoint: POST /jobs/reset-notifications
Schedule: Daily at midnight UTC (QStash cron)
  Reset notification_sent_today = false for all users
  Prevents notification spam (max 1 push per day rule)
```

**Security:** All `/jobs/*` endpoints verify `Upstash-Signature` header — prevents external triggering.

**Job summary:**

| Job | Schedule | LLM calls | Priority for v0.1 |
|---|---|---|---|
| Deadline scanner | Hourly | 0 | Must have (push notifications) |
| Urgency decay | Every 6h | 0 | Must have (scoring) |
| Post-conversation | After each chat | 1-2 | Must have (embeddings, dedup) |
| Graph processing | After each chat (5s) | 1-2 | Graph ingest + feedback (async, not in request path) |
| Calendar sync | Every 4h | 0 | Must have (calendar context) |
| Pattern detection | Daily | 1-3 | Config-driven LLM analyses (config/patterns.yaml) |
| Notification reset | Daily midnight | 0 | Must have (prevents >1 push/day) |

---

## 7. LLM Call Budget Per Interaction

| Path | LLM Calls | Notes |
|------|-----------|-------|
| Brain dump (1-2 items) | 1-2 | Classification + extraction often one call |
| Brain dump (5+ items) | 2 | Classification + extraction/enrichment |
| "What should I do?" | 1 | Scoring is code, formatting is LLM |
| "What's coming up?" | 0-1 | Often pure DB query + template |
| "Done" | 0-1 | Match can be code, ack can be template |
| "Bad day" | 1 | Emotional response needs LLM nuance |
| Onboarding | 0 | Canned response |
| Meta (help/cancel) | 0 | Canned responses |
| Conversation | 1 | Needs LLM for natural response |

**Target: average 1-2 LLM calls per user message in the request path.** Post-processing adds 1-2 async LLM calls (graph ingest + feedback) that don't block the response.

---

## 8. Proactive Messaging — When Unspool Speaks First

These are moments where the AI initiates rather than responds. This is what makes Unspool feel alive — it's not just a tool you talk to, it's something that notices, remembers, and gently reaches out.

### 8A. On App Open (presence-triggered)

These fire once per session, when the user opens the app. They appear as a message already waiting in the chat before the user types anything.

#### Hard deadline imminent

```
User opens app
    │
    ▼
  Check: any items with hard deadline < 24 hours?
    │
    YES (1 item):
      "hey — rent is due tomorrow. just a heads up."
    │
    YES (2+ items):
      "two things coming up: rent tomorrow
       and thesis draft due friday."
    │
    NO → no proactive message, just quiet chat waiting
```

**Rules:**
- Only hard deadlines. Soft deadlines wait for the user to ask.
- Consolidate multiple into one message, never multiple messages.
- Action buttons attached: `done` / `remind me later` / `I know`
- Tone: factual, not nagging. "just a heads up" not "don't forget!"

#### Something slipped

```
User opens app after 3+ days of absence
  AND has items with soft deadlines that have passed
    │
    ▼
  "been a few days — the supervisor email is getting stale.
   want to deal with it or let it go?"
    │
  Buttons: [deal with it] [let it go] [show me everything]
```

**Rules:**
- Only fires once per absence period, not every open.
- "Let it go" is always an option — no guilt.
- Maximum 1-2 items mentioned. If more have slipped, summarize: "a few things have gone stale."

#### Calendar conflict detected

```
Background job synced calendar AND found conflict with open items
    │
    ▼
  "you've got back-to-back meetings thursday 10am-2pm.
   might want to push the thesis work to another day."
```

**Rules:**
- Only fires when there's a genuine conflict (not just "you have a meeting").
- Requires calendar to be connected (Google OAuth).
- Never mentions specific meeting details from calendar in a way that feels surveillance-y. "meetings thursday" not "meeting with Dr. Chen about chapter review."

#### Good news / momentum

```
User completed 3+ items in their last session
    │
    ▼
  On next open:
  "you knocked out 4 things last time. solid."
```

**Rules:**
- Brief. One line. Not a celebration parade.
- Only after genuinely productive sessions (3+ completions), not after 1 "done."
- Doesn't ask for anything — just acknowledges.

#### Long absence, gentle re-entry

```
User opens app after 7+ days
    │
    ▼
  "hey. no pressure — I've been keeping track.
   want to see what's still on the plate, or start fresh?"
    │
  Buttons: [show me what's open] [start fresh]
```

**Rules:**
- "Start fresh" mass-expires all open items. Clean slate. No guilt.
- This is critical for ADHD users who abandon systems — re-entry should feel welcoming, not overwhelming.
- Never: "you've been gone for 12 days and have 23 overdue items!"

---

### 8B. Mid-Conversation Piggybacks

These attach to the end of a normal response. The AI responds to what the user said AND adds relevant context it noticed.

#### Calendar awareness during dumps

```
User: "need to write the thesis introduction this week"
    │
    ▼
  AI processes as BRAIN_DUMP → stores item
  THEN checks calendar context (already in hot context)
    │
    Calendar shows meetings mon-wed:
    │
    ▼
  "got it — thesis intro this week. heads up though,
   your calendar shows meetings monday through wednesday
   afternoon. thursday might be your best window."
```

**Rules:**
- Only when calendar data genuinely conflicts with or informs the dump.
- Don't mention calendar for every dump — only when timing matters.
- Natural language, never "according to your Google Calendar..."

#### Overcommitment detection

```
User dumps 5 new things
  AND already has 15+ open items
  AND completion rate last 7 days is low
    │
    ▼
  Normal acknowledgment of the 5 items
  THEN:
  "honestly though, you've got a lot on your plate right now —
   want me to pick the 3 that actually matter this week?"
    │
  Buttons: [yes, pick 3] [I'll handle it] [show me everything]
```

**Rules:**
- Threshold: 15+ open items AND dumps outpacing completions.
- Don't fire this every time they dump. Maybe once a week max.
- The "I'll handle it" option is respected — no follow-up pushback.

#### Related idea surfacing (post-MVP)

```
User: "stuck on the fleet optimization chapter"
    │
    ▼
  Semantic search against LONG_TERM tier finds:
    3 weeks ago user stored: "interesting idea — transformer
    attention mechanisms for scheduling"
    Similarity score > 0.8
    │
    ▼
  Normal response about the chapter
  THEN:
  "you mentioned something about transformer attention
   for scheduling a few weeks ago — could that be
   relevant here?"
```

**Rules:**
- Similarity threshold must be high — false connections are worse than no connections.
- Never more than one related idea per response.
- Phrased as a question, not an assertion: "could that be relevant?" not "you should use this."

#### Recurring pattern noticed

```
Tier 3 pattern detection found:
  User dumps most on Sunday evenings
  User rarely completes tasks on Mondays
  Confidence: high (observed 4+ weeks)
    │
    ▼
  Next time user dumps on Sunday evening:
  Normal acknowledgment
  THEN:
  "you tend to dump a lot on sundays — mondays seem tough
   though. want me to nudge you about these tuesday instead?"
    │
  Buttons: [yes, tuesday] [no, tomorrow is fine]
```

**Rules:**
- Only surface a pattern when confidence is high (4+ weeks of data).
- Ask before acting on the pattern — don't silently reschedule.
- Maximum one pattern insight per week. Don't become a behavioral analyst.

#### Energy mismatch warning

```
User asks "what should I do?"
  AND user's recent messages are short, low-energy
  AND the highest-urgency item is HIGH energy
    │
    ▼
  "the thesis chapter is technically the most urgent,
   but you seem low-energy right now.
   want something smaller first?"
    │
  Buttons: [give me the thesis] [something smaller] [nothing right now]
```

**Rules:**
- Energy inference comes from: message length, tone, time since last interaction, recent emotional signals.
- "Nothing right now" is always an option.
- If user picks the hard task anyway, respect it — don't second-guess.

---

### 8C. Push Notifications (app is closed)

Maximum one per day. The only time Unspool reaches out without the user initiating.

#### Hard deadline in 24 hours

```
Background job: /jobs/check-deadlines (hourly)
    │
    ▼
  Found: item with hard deadline < 24h
  AND notification_sent_today = false for this user
    │
    ▼
  Push notification:
    Title: "unspool"
    Body: "rent due tomorrow"
    │
  On tap → opens app with message waiting:
    "rent is due tomorrow."
    Buttons: [done] [remind me in 4 hours] [I know]
```

**Rules:**
- Short. Factual. No emojis, no "don't forget!"
- Multiple items → consolidate: "rent tomorrow + thesis draft friday"
- Quiet hours: suppress 1am-7am user local time.
- Mark notification_sent_today = true after sending.

#### Same-day escalation (only exception to 1/day rule)

```
Previous 24h notification was sent yesterday
  AND item is still open
  AND deadline is within 3 hours
    │
    ▼
  Push notification:
    Title: "unspool"
    Body: "thesis draft due in 3 hours"
```

**Rules:**
- This is the ONLY scenario where a second notification in 24h is acceptable.
- Only for hard deadlines on the same day.
- If the user dismissed the first notification and still hasn't acted, this is the final nudge.

#### Weekly summary (opt-in, post-MVP)

```
AI offers after 2+ weeks of active use:
  "want me to send you a weekly heads-up
   with what's on your plate?"
    │
  Buttons: [yes] [no thanks]
    │
  If yes → weekly push notification:
    Title: "unspool"
    Body: "5 things open, 2 coming up this week"
    │
  On tap → opens app with summary message waiting
```

**Rules:**
- Opt-in only. If user says no, never asked again.
- User can opt out any time: "stop the weekly summary."
- Sent at a time inferred from user's typical active hours (not 9am — they might not wake up then).

---

### 8D. NEVER send proactive messages for:

```
NEVER:
  ✗ "You haven't checked in today/this week"     (manipulative)
  ✗ Soft deadlines                                 (not urgent enough)
  ✗ Ideas or parked items                          (not urgent by definition)
  ✗ Completed item celebrations                    (not worth an interruption)
  ✗ Product updates or announcements               (not a marketing channel)
  ✗ Feature tips or tutorials                      (not a tour guide)
  ✗ "Your streak is X days!"                       (not gamification)
  ✗ Multiple push notifications in one day         (except same-day escalation)
  ✗ Any proactive message during emotional moments (user said "bad day" — leave them alone)
```

---

### 8E. Ambient Awareness (rare, delightful, post-MVP)

These are the "how did it know?" moments. Very infrequent. Build trust over time.

#### Completion milestone

```
User has completed 50 items total (lifetime)
    │
    ▼
  Somewhere in a normal response, casually:
  "that's 50 things you've handled through here, by the way."
```

No fanfare. No badge. Just a quiet fact.

#### First month

```
User has been active for 30 days
    │
    ▼
  On open:
  "it's been a month. you've been pretty consistent."
```

Not a celebration. Just a human observation.

#### Weather + task correlation (if weather API added)

```
User has "go for a run" as recurring soft item
  AND weather API shows sunny day
    │
    ▼
  On open:
  "nice day out — good running weather if you're up for it."
```

Extremely subtle. A gentle noticing, not a command.

---

### Proactive Messaging Summary

| Trigger | When | Tone | Frequency |
|---|---|---|---|
| Hard deadline imminent | App open | Factual, brief | Every open if deadline <24h |
| Something slipped | App open after 3+ day absence | Gentle, offers "let it go" | Once per absence |
| Calendar conflict | App open | Helpful, informational | Only when genuinely relevant |
| Momentum acknowledgment | App open after productive session | Brief, warm | Once per session |
| Long absence re-entry | App open after 7+ days | Welcoming, no guilt, offers fresh start | Once per absence |
| Calendar context in dump | Mid-conversation | Natural, as-if-friend-knows | When dumps conflict with calendar |
| Overcommitment detection | Mid-conversation | Honest, offers to filter | Max once per week |
| Related idea surfacing | Mid-conversation | Curious, phrased as question | When similarity is high |
| Recurring pattern | Mid-conversation | Observational, asks before acting | Max once per week |
| Energy mismatch | Mid-conversation | Empathetic, offers alternative | When inference conflicts with suggestion |
| Hard deadline push | Push notification | Short, factual | Max 1/day |
| Same-day escalation | Push notification | Urgent but brief | Only exception to 1/day |
| Weekly summary | Push notification (opt-in) | Neutral, informational | Weekly if opted in |
| Completion milestone | Mid-conversation | Casual, factual | At 10, 50, 100, etc. |
| First month | App open | Warm, brief | Once |