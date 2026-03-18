# Unspool Memory Architecture — First Principles

## The Core Insight

Unspool is a second brain. Not a task manager, not a chatbot — an external mind that compensates for the parts of cognition that break down in ADHD: recall, prioritization, and pattern synthesis.

The ideal system would store every thought the user ever had and, at any moment, read through all of them to decide what to do. Everything we build is an approximation of that ideal, constrained by context windows, latency, and cost.

## The Raw Stream

All data enters as a single append-only, immutable stream. Every entry has a timestamp. Nothing is classified, categorized, or transformed at the point of entry.

The stream contains six columns. Not all columns are populated in every row.

### The Six Columns

#### 1. User Thought (UT)
What the user types. Raw, unstructured, messy. A single message might contain tasks, facts, emotions, corrections, questions, and noise all mixed together. This is the primary input — everything else derives from it.

#### 2. Unspool Thought (UnsT)
What Unspool responds. This is also part of the stream because Unspool's responses are commitments. "I'll remind you at 8" is a promise. "Your mom's birthday is March 22" is an assertion that could be wrong. "You wrote 3 pages last week" is evidence Unspool used to reframe the user's self-perception. The user's mind processes Unspool's thoughts just like any other input — they affect what the user remembers, feels, and does.

#### 3. User Memory (UM) — Hidden
What the user actually remembers in their head. We can never see this directly. But it matters because it's the gap between what the user knows and what Unspool knows that creates the value. If the user already remembers something, surfacing it is noise. If the user forgot something, surfacing it is the entire point.

We can speculate about UM based on:
- What the user mentions vs. doesn't mention
- How long since they last referenced something
- Whether they ask Unspool for information they were previously told
- Emotional signals (guilt about forgotten tasks implies they partially remember)
- Time of day, energy level, and cognitive load (all affect recall)

UM is the column we're trying to influence. Every Unspool Thought is an attempt to place the right information into the user's working memory at the right time.

#### 4. Unspool Memory (UnsM)
What Unspool derives and stores from the stream. This is the only column we fully control. It's a derived view — a lossy compression of the raw stream optimized for recall. Everything in UnsM is rebuildable from the raw stream (UT + UnsT + UA + UnsA). If UnsM contradicts the raw stream, the raw stream wins.

UnsM is NOT a separate database of "memories." It's an index, a cache, a set of materialized views over the raw stream that make it queryable without reading every message.

#### 5. User Action (UA)
Things the user does in the real world or in other apps. We learn about these through the stream — the user tells us "paid rent," "called mom," "sent the email." We also learn about them through connected services — calendar events appear, confirmation emails arrive. User actions are facts that enter the stream with timestamps.

#### 6. Unspool Action (UnsA)
Things Unspool does beyond responding. Sending a push notification. Creating a calendar event. Scheduling a reminder. Triggering a background job. These are also part of the stream — they're commitments and facts that may need to be recalled later. "I already sent a notification about this" is relevant context for deciding whether to notify again.

## Properties of the Raw Stream

1. **Append-only.** Nothing is ever modified or deleted. A correction is a new entry that supersedes a previous one. "Actually the wedding is June 15 not June 14" doesn't edit row 8 — it's a new row that the system must reconcile.

2. **Immutable.** The stream reflects reality as it was understood at each point in time. This history has value — knowing that the user originally said June 14 then corrected to June 15 tells you something about their certainty.

3. **Multi-source.** The stream includes user messages, system responses, calendar syncs, external data fetches — anything that enters the system. All entries are timestamped and attributed to their source.

4. **Both sides of the conversation.** Unspool's responses are in the stream too. They are facts, commitments, and assertions that affect the user's mental state and that Unspool must be consistent with.

## Derived Views (UnsM)

Everything Unspool "knows" is derived from the raw stream. These derived views exist purely to make the raw stream queryable at scale. They are:

- **Rebuildable** — can be regenerated from the raw stream at any time
- **Mutable** — updated when new information enters the stream
- **Potentially duplicated** — the same fact may exist in multiple views for different access patterns
- **Internally consistent** — when a fact changes, all views that reference it must update
- **Never authoritative** — on conflict with the raw stream, the raw stream wins

The specific shape of derived views should be determined by what actions need them. We define the actions first, then design the views to serve them.

## The Consistency Problem

A single thought can update many derived views. "Actually the wedding is June 15" needs to propagate to:
- Any stored fact about the wedding date
- Any scheduled reminder tied to June 14
- Any temporal relevance calculation
- Any embedding that encoded "June 14 wedding"

The solution is a **facts view** — a master index of derived facts, each linked to every other derived view that uses it. When a new thought arrives:
1. Extract facts from it
2. Check each against the facts view
3. If new → add to facts view, propagate to relevant derived views
4. If contradiction → update the fact, follow links to update all dependent views
5. If confirmation → update "last verified" timestamp (increases confidence)

This is a write-through cache pattern. The facts view is the single reconciliation point.

## What Unspool's Mind Does

Borrowing from cognitive science, Unspool's mind performs six operations:

1. **Remember** — absorb a thought into the stream, extract derived facts
2. **Recall** — given current context, activate relevant memories from the derived store
3. **Decide** — from active memories, determine what matters right now
4. **Act** — do something (respond, notify, schedule) which creates new stream entries
5. **Forget** — reduce activation of stale, unverified, low-salience memories
6. **Synthesize** — compress many memories into higher-level understanding (patterns, preferences)

These map to the ADHD deficit: **Recall** (things don't surface when they should), **Decide** (too many things active at once → paralysis), and **Synthesize** (patterns don't form because working memory is overloaded).

## All Memories Are Equal

There is no typing of memories at the storage level. A task, a fact, an event, a preference, a pattern — they're all just memories. The reason: any memory can be relevant to any moment. "Mom lives in Portland" is a fact. "Buy flight tickets" is a task. "User avoids planning on Mondays" is a pattern. But when the user says "I should visit mom for Easter," all three are relevant simultaneously, and their power is in the connection, not the category.

Memories may carry properties intrinsic to their content:
- **Whether it has a completion state** — "buy milk" can be done, "mom lives in Portland" can't
- **Whether it's time-sensitive** — "rent due Friday" has temporal urgency, "cousin likes pottery" doesn't
- **Confidence level** — "wedding is June 14 I think" vs "rent is due Friday for real"
- **Connections to other memories** — which other memories relate to this one

But these are properties, not types. The retrieval system uses all properties simultaneously when deciding what to surface — recency, relevance, time-sensitivity, completion state, confidence, connections — scored together, not routed through type-based pipelines.

## The Scaling Problem

### The Ideal vs. Reality

The lowest-effort architecture: take the entire raw stream and feed it to an LLM at each timestep. The LLM has full context, can make perfect decisions, and we need zero derived views. This works for the first week. It breaks as context grows.

The naive fix — compress the stream into "current facts" — loses critical information. If a user has corrected a fact 5 times, that correction pattern is itself an observation. It tells you about the user's certainty, their relationship with that topic, maybe even their cognitive state. Flattening to "current value" destroys this signal.

### The Dynamic Analysis Problem

What's worth observing varies per user. Maya's thesis anxiety pattern is unique to her. Another user might have a pattern around medication timing, or seasonal mood shifts, or a tendency to overcommit on Wednesdays. Hardcoding "observe these specific patterns" means we'll miss the ones that matter most for each individual.

This suggests the system needs to **dynamically create observations** — noticing patterns that aren't pre-defined, and building user-specific understanding over time. Some of this is LLM-driven (synthesis), but the system should also recognize when a new "view" is forming and persist it.

### Three Tiers of Views

#### Tier 1: Standard Views (same structure for all users)
Maintained automatically. These are the minimum viable context for any interaction.

- **Calendar** — time-anchored events from external sources (Google Calendar) and user-stated commitments with dates. Structured data, no LLM needed to maintain.
- **People** — who exists in the user's world, basic relationship context. "Sarah = friend, pottery, birthday April 2." Updated when people are mentioned.
- **Profile** — communication preferences, timezone, energy patterns, how they like to be talked to. Built from observation, not settings.
- **Open commitments** — things with a completion state that aren't done yet. "Email advisor" = open. "Paid rent" = closed. Each tracks: what it is, when it was mentioned, any deadline, current confidence.
- **Current facts** — latest version of each known fact, with provenance (which stream entry it came from) and confidence level.

#### Tier 2: Synthesized Views (same structure, unique content per user)
Built over time through periodic analysis. These capture understanding, not just data.

- **Behavioral patterns** — "works in bursts not marathons," "can't do cognitively hard tasks after shifts," "overthinks written communication." These are observations about HOW the user operates.
- **Effective strategies** — what worked for this specific user. "One chart at a time" for Maya's thesis. "Text instead of call when overwhelmed." These are learned interventions.
- **Emotional patterns** — recurring emotional responses to specific topics or situations. "Thesis = anxiety," "mom calls = guilt + warmth." Shapes tone and timing of responses.
- **Relationship dynamics** — deeper than the People view. "Mom = support + pressure source, asks about thesis." "Sarah = close friend, academic peer, source of conference info."
- **Meta-observations** — patterns about patterns. "User has corrected wedding date 3 times — low confidence in this fact." "User says 'tomorrow' about thesis but never follows through — planning doesn't work for this topic."

#### Tier 3: Emergent Views (unique structure per user)
These don't fit any pre-defined template. They emerge when the system notices it keeps reasoning about something that doesn't have a view yet.

Examples that might emerge for Maya:
- A "thesis progress" view tracking sections, pages written, work sessions — because this project spans weeks and has internal structure
- A "shift schedule" view because her work pattern directly affects what she can do on any given day
- A "Portland travel" view aggregating mom, easter, bus ticket, packing into one context

The system should be able to notice "I keep needing to assemble the same information" and create a persistent view for it. This is the hardest tier to implement but the most powerful — it's where the system genuinely adapts to the individual.

### Right Tool for the Job

Not everything needs an LLM. Different operations suit different methods:

| Operation | Method | Why |
|-----------|--------|-----|
| Calendar view maintenance | Structured data sync | Deterministic, no interpretation needed |
| "How many times was X corrected" | SQL aggregation | Counting, not reasoning |
| "What time does user usually message" | Statistical analysis | Pattern in timestamps, not content |
| "Is this a contradiction of a previous fact" | Embedding similarity + LLM confirmation | Needs semantic understanding |
| "What strategy works for this user's thesis anxiety" | LLM synthesis over behavioral history | Requires deep contextual reasoning |
| "Should we surface X right now" | Hybrid — rule-based filters (time, recency) + LLM judgment (relevance, emotional timing) | Some dimensions are computable, others need judgment |
| Deadline proximity alerts | Time comparison | Pure math |
| Embedding generation | Embedding model | Specialized, not general LLM |
| "User seems overwhelmed right now" | LLM reading recent messages | Emotional inference needs language understanding |

The architecture should route each operation to the cheapest sufficient method. LLM calls are expensive — use them where judgment and synthesis are genuinely needed, not for things a SQL query or a timer can handle.

## The Simulation

See the plan file (`structured-humming-unicorn.md`) for a full 44-day, 81-row simulation of all six streams for a single user (Maya, 27, grad student, ADHD). The simulation demonstrates how the streams interact over time and what Unspool needs to know at each moment to produce the right response.

## Next Steps

- Analyze the simulation to determine what Unspool needed to know at each row → defines required derived views
- Identify gaps in the simulation (corrections, recurring tasks, multi-person coordination, idea connections)
- Define the action types and what data each action needs → shapes the derived view schema
- Design the derived view schema and consistency propagation mechanism
- Map this architecture onto the existing codebase
