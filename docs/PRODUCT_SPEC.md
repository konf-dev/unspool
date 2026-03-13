# Product Spec: Unspool

**Domain:** unspool.life  
**Version:** 0.1 MVP  
**Date:** March 2026  
**Status:** Pre-launch

---

## One-line pitch

An AI that remembers everything so you don't have to. No app to organize. No inbox to clear. Just talk.

---

## The Problem

### Productivity tools are designed for people who can already be productive

Every task manager, planner, calendar app, and note-taking system on the market is built on the same hidden assumption: the user has the executive function to maintain the system. They assume you can decide where something goes, how urgent it is, what category it belongs to, and when you'll do it — all at the moment of capture.

For people with ADHD (and honestly, for a much larger population of overwhelmed, non-neurotypical, or simply overloaded humans), these are the exact cognitive tasks that are broken. Asking an ADHD brain to categorize a task before saving it is like asking someone with a broken leg to take the stairs to the elevator.

### The cycle of productivity tool failure

The pattern is painfully consistent:

1. **Discovery.** You find a new tool (Notion, Obsidian, Todoist, Motion, a physical planner). It looks clean and promising. Dopamine spike.
2. **Setup.** You spend hours configuring it — databases, templates, categories, views. This feels productive. It isn't.
3. **Honeymoon.** You use it religiously for 3 days to 2 weeks. Everything is organized.
4. **Friction accumulates.** The system gets heavier the more you use it. Notion fills with pages. Obsidian gets tangled. Todoist becomes a guilt list. Every new item requires a decision: which project? what priority? what tag?
5. **Abandonment.** The cognitive cost of maintaining the system exceeds the benefit. You stop using it. The tool that was supposed to reduce cognitive load has become the cognitive load.
6. **Guilt.** You now have an abandoned system staring at you, full of outdated tasks you'll never look at.
7. **Repeat from step 1.**

### The specific pain points we're solving

**Decision fatigue at the point of capture.** Every "where does this go?" question costs a spoon. When you're out of spoons, you capture nothing. Things fall through the cracks. Not because you forgot — because the act of remembering was too expensive.

**Categories don't match how ADHD brains work.** "Work," "personal," "college," "health" — these are neat boxes for neat brains. In reality, everything is a giant jumbled mess. Everything feels equally important. Paying rent and preparing for a standup exist in the same undifferentiated cloud of "things I should be doing." Maintaining separate lists, pages, or databases for separate life areas is itself a source of overwhelm.

**Priority is paralyzing.** When everything feels important and everything feels urgent, being asked to rank things is asking you to solve the exact problem you need help with. Most tools outsource prioritization back to the user and call it "flexibility."

**Time-based systems assume you live on a clock.** Most planners divide the world into days, mornings, evenings, and weeks. Many people with ADHD don't operate this way. They sleep when sleepy, wake when their eyes open, and don't have a consistent "most productive time of day." Their energy and focus are not tied to the clock — they're tied to internal states that shift unpredictably. "Plan your morning" is meaningless when morning is a fluid concept.

**The tool gets heavier over time.** This is the critical failure. Every productivity tool accumulates: tasks pile up, notes multiply, views get cluttered, badges turn red. The more you use it, the more it demands from you. Eventually, opening the app itself triggers anxiety — the Wall of Awful.

---

## The Insight

### The system should get smarter without getting heavier

The tool should absorb more information over time and use it to serve you better — without any of that accumulation being visible or requiring maintenance. The chat log scrolls away. You never have to go back to it. The AI holds the state, not you.

### Categories are a UI for people who can already prioritize

If you could sort things into "work" vs "personal" vs "urgent" vs "important," you wouldn't need the tool. For the target user, the act of categorizing IS the bottleneck. So: no categories. Ever. Not even hidden ones that "the AI manages for you." The moment the AI says "you have 3 work tasks and 2 personal tasks," it's forcing a context switch between mental frames. That's a decision. That's a spoon.

### "You're here" is the only signal that matters

Instead of time-of-day scheduling, the primary trigger is presence. Every time the user opens the chat, the AI treats it as: "they're awake and available." It offers the most pressing thing right then. If the user disappears for 18 hours, it doesn't spam them. The moment they come back, it recalibrates. No guilt, no missed-notification anxiety.

### One thing, not a list

When the user asks for help, the AI gives them one thing to do — not a prioritized list. The list IS the problem. One item, calibrated to what's most time-sensitive and what the user can handle right now. If they can't do it, they say so, and the AI gives a different one.

---

## The Product

### What it is

A single chat interface. You type or voice-note anything — tasks, ideas, worries, deadlines, random thoughts, stream of consciousness. That is the only interaction surface.

No dashboards. No databases. No views to configure. No settings page. No onboarding wizard. No "create your first project." No categories to choose from. No weekly review ritual. No integrations page.

First interaction: you open it, you see a chat box, you type. Done.

### Core interaction loop

**1. You dump stuff in.**

Messy, unstructured, whatever comes to mind. Multiple things in one message. Half-formed thoughts. Duplicates. The AI acknowledges with one short line confirming what it understood and moves on:

> *"got it — supervisor email, I'll nudge you in a couple days"*  
> *"noted, I'll remind you about flights next week"*  
> *"captured that idea about reinforcement learning for fleet scheduling"*

No categorization shown. No priority level. No follow-up questions unless something is genuinely ambiguous.

**2. You ask for direction.**

"What should I do?" → One thing. Not a list. The AI picks based on what's closest to blowing up that you can actually handle right now.

"What's coming up?" → Only things with real consequences in the next 48 hours. Not a full inventory.

"Did I ever think about X?" → Searches your history and surfaces related past dumps.

**3. You report back (or don't).**

"Done" → The AI marks it off. Maybe a small acknowledgment: *"nice, that one's been sitting for a week."*

"Can't today" / "bad day" / "overwhelmed" → The AI quietly deprioritizes everything soft. No guilt. No red badges.

**4. You leave.**

The AI waits. No notifications unless a hard external deadline is approaching. No "you haven't checked in today!" messages.

### How the AI thinks (invisible to the user)

**Two dimensions, no categories:**

**Dimension 1: "When does this blow up if I ignore it?"**

- Hard deadline with external consequences (rent, standup, submission deadline) → the AI knows the date and counts down.
- Soft deadline with social consequences (replying to supervisor, scheduling a meeting) → the AI infers a reasonable window from the language ("soon" → ~2 days, "next week" → 5-7 days, "at some point" → parked).
- No deadline (ideas, "I should look into X") → stored, surfaced only when relevant.

The user never assigns urgency. The AI infers it from language and from real-world knowledge (it knows rent has late fees, it knows standups are daily, it knows PhD application deadlines are hard).

**Dimension 2: "How much energy does this take?"**

- Low energy: reply to an email, buy laundry detergent, check a link.
- Medium energy: schedule an appointment, prep for a meeting, do a small chore.
- High energy: write a thesis chapter, build a project, have a difficult conversation.

The AI learns energy patterns over time:

- When the user dumps 15 things at once → probably overwhelmed → offer the smallest, easiest win to build momentum.
- When the user proactively asks "what should I do" → they have some energy → offer something meaningful.
- When the user says "done" on multiple things in a row → they're in flow → don't interrupt, queue the next thing.
- When the user goes quiet for a long time → don't nag, but note that things may be slipping.

### Fuzzy deadlines

Not everything has a date. The AI handles ambiguity natively:

| What the user says | What the AI infers |
|---|---|
| "Rent due on the 1st" | Hard deadline. Remind 3 days before, then 1 day before. |
| "Need to reply to supervisor soon" | Soft, ~2 day window. Gentle nudge. |
| "Should think about booking flights home" | Very soft. Nudge in ~5 days: "still want to look at flights?" |
| "PhD applications... eventually" | Parked. Surface when the user asks about their plate or when a related trigger appears. |
| "Interesting paper on RL for fleet optimization" | Idea. No deadline. Surface when the user mentions thesis or related topics. |

### The anti-accumulation rule

The user never sees a growing list. No inbox count. No overdue badge. No "you have 47 tasks." The AI absorbs everything and only surfaces what's relevant right now — either when asked, or proactively when something is genuinely time-sensitive.

If something becomes irrelevant because time passed, the AI quietly deprioritizes it. No guilt, no red markers, no "you have 12 overdue items." Things that were never done just fade. If they were important, they'll come up again. If they don't, they weren't.

### Clock-free design

The product does not think in time-of-day. It thinks in relative time and real deadlines.

- **No "plan your day" ritual.** The app never asks the user to sit down and plan. There is no daily view, no weekly view, no calendar grid.
- **No time-based reminders by default.** The default nudge is "when you next check in" or "X hours before this deadline." The trigger is presence, not the clock.
- **Exception: hard external events.** If standup is at 10am on Thursday, that gets a clock-based notification because the world imposed it. The AI distinguishes between user-imposed deadlines (flexible) and world-imposed deadlines (rigid).
- **No "most productive time" assumptions.** The AI doesn't assume mornings are for deep work. It calibrates based on observed behavior, not circadian norms.

### Idea correlation (post-MVP, but core to the vision)

Over time, the AI builds a web of everything the user has mentioned. When they dump something new, it can connect it to past dumps:

> User (week 1): "interesting idea — using transformer attention mechanisms for scheduling"  
> User (week 4): "stuck on thesis chapter 4, need a fresh angle for the fleet optimization problem"  
> AI: "you mentioned something a few weeks ago about attention mechanisms for scheduling — could that be relevant here?"

This is the "second brain" that Notion and Obsidian promise but require you to maintain manually. Here, it happens automatically from the chat history.

---

## What this is NOT

- **Not a calendar app.** It may read your calendar for context (to know about upcoming meetings), but it doesn't show you a calendar view.
- **Not a to-do list.** There is no list view. The AI holds the list internally; the user never sees it as a list.
- **Not a note-taking app.** You don't go back and browse notes. You dump, the AI absorbs, and it surfaces things when relevant.
- **Not a project management tool.** No boards, no columns, no sprints.
- **Not a general AI chat assistant.** It doesn't answer trivia or write essays. It does one thing: manage the chaos in your head.

---

## MVP Scope (v0.1) — Weekend Launch

### v0.1 DOES:

- **Accept free-form text input** — any message, any format, any length. Multiple items in one message. Messy is fine.
- **Accept voice input** — Web Speech API, transcript appears in input for review before sending. Swappable to Whisper API later.
- **Acknowledge and confirm understanding** — one short line per dump, showing what it understood. No follow-up questions unless critically ambiguous.
- **Infer deadlines and urgency from natural language** — "soon," "by next week," "on the 1st," "at some point" all handled without the user explicitly setting anything.
- **Store everything persistently** — nothing is lost. The AI remembers across sessions.
- **Answer "what should I do?"** — returns one item, the most time-sensitive thing the user can handle right now.
- **Answer "what's coming up?"** — returns only items with real consequences in the next 48 hours.
- **Mark things done** — user says "done with X" or "finished the email" and it's handled.
- **Graceful deprioritization** — user says "bad day" or "can't today" and everything soft gets pushed without guilt.
- **Streaming responses** — AI text appears word by word, not all at once. Feels responsive and alive.
- **Push notification for hard deadlines** — maximum one per day, only when something with real consequences is within 24 hours. Respects the "quiet respect" principle.
- **Google Calendar integration** — read-only, bundled with Google Sign-In. One consent screen. AI knows about your upcoming meetings.
- **PWA installable to home screen** — one tap install, fullscreen, app icon, no browser chrome.
- **Rate-limited free tier** — 10 messages/day, full functionality. One-tap upgrade to $8/month unlimited inside the chat.

### v0.1 does NOT:

- Idea correlation / connecting past dumps to current context.
- Email integration.
- Apple Calendar or Outlook integration (Google only).
- Any visual UI beyond the chat box.
- Any settings, preferences, or configuration.
- Analytics, streaks, or gamification.
- Multiple notifications per day. Ever.
- Re-engagement notifications ("you haven't checked in!"). Ever.

---

## Data Model (Minimal)

Each item the AI extracts from user input:

| Field | Type | Description |
|---|---|---|
| `id` | uuid | Unique identifier |
| `user_id` | uuid | Supabase auth user ID (required for multi-tenant) |
| `raw_text` | string | The original text the user typed |
| `interpreted_action` | string | What the AI understood as the action |
| `deadline_type` | enum | `hard` / `soft` / `none` |
| `deadline_at` | datetime, nullable | Inferred deadline, if any |
| `urgency_score` | float | AI-inferred, 0-1, decays/increases over time |
| `energy_estimate` | enum | `low` / `medium` / `high` |
| `status` | enum | `open` / `done` / `expired` / `deprioritized` |
| `created_at` | datetime | When the user dumped it |
| `last_surfaced_at` | datetime, nullable | Last time the AI showed this to the user |
| `nudge_after` | datetime, nullable | Earliest time to surface this again |

No category field. No priority field the user ever sees. No project field. No tags.

---

## Competitive Landscape

| Product | What it does well | Where it fails for our user |
|---|---|---|
| **OpenClaw** | Self-hosted, proactive, multi-channel, extensible | Power-user dev tool. Complex setup. Security concerns. Not ADHD-designed. |
| **Saner.AI** | ADHD-focused, note + email + calendar in one interface | Still a "second brain" that requires organizing. Doesn't execute. Buggy mobile. |
| **alfred_** | Autonomous email triage, zero-maintenance | Email-only. No brain dump. No idea capture. $25/month. |
| **Motion** | AI auto-scheduling, time-blocking | Requires structured task entry. $19-29/month. Assumes clock-based living. Complex setup. |
| **Notion/Obsidian** | Flexible, powerful, customizable | Flexibility IS the problem. Setup is overwhelming. Accumulates. Requires maintenance. |
| **Todoist/TickTick** | Simple task capture | Still a list that grows. Still requires priority decisions. Guilt badges. |
| **Tiimo/rivva** | ADHD-specific, visual planning | Assumes routines and daily planning rituals. Clock-based. |
| **Dola** | Chat-based calendar in WhatsApp | Calendar only. No task management. No memory. No prioritization. |

### Our gap

Nobody has built: a single chat interface where you brain-dump everything with zero decisions, and the AI handles classification, urgency inference, fuzzy deadline interpretation, energy-aware prioritization, and proactive surfacing — all without the user ever seeing a list, a category, a dashboard, or a growing inbox.

---

## Design Principles

1. **Zero decisions at capture.** The user types. That's it. No "which project?" No "what priority?" No "when?" The AI figures it out.

2. **One thing at a time.** When the user asks for help, they get one item. Not a list. The list is the enemy.

3. **No accumulation.** The user never sees a growing backlog. Things that become irrelevant fade silently. No guilt.

4. **No clock assumptions.** The product works for someone who wakes at 6am and someone who wakes at 3pm. Time-of-day is irrelevant unless the external world imposed it.

5. **Presence-triggered, not time-triggered.** The AI activates when you show up, not when the clock says so.

6. **The system gets smarter, not heavier.** More use = better understanding of the user. More use ≠ more things to maintain.

7. **Setup is nothing.** First interaction is typing a message. There is no step 2.

8. **Graceful failure.** If the user disappears for a week, nothing breaks. They come back, pick up where they left off. No "you missed 47 things" guilt trip.

9. **Quiet respect.** When the app pings you, it matters. Maximum one notification per day, only for hard deadlines. Silence is not a bug — it's the product working correctly. No re-engagement manipulation.

10. **One price, no decisions.** Free works fully. Paid removes one limit. No tiers, no comparisons, no annual vs monthly. The pricing decision should cost zero spoons.

---

## Notification Philosophy — "Quiet Respect"

### The problem with notifications

Most apps train users to ignore notifications by sending too many. Push notifications become noise — swiped away reflexively, generating anxiety even when dismissed. For ADHD users, notification overload is especially damaging: each buzz is an involuntary context switch, a spike of "what am I forgetting?" stress, and another reason to uninstall the app entirely.

The re-engagement notification ("We miss you!", "You haven't checked in today!") is particularly toxic. It turns the tool into a guilt machine — the exact opposite of what an ADHD brain needs. It says: "you failed to use me." That's not a reminder, it's a judgment.

### Our rules

**Maximum one push notification per day. Period.** Not one per item — one total. If rent is due tomorrow AND your thesis draft is due tomorrow, that's still one notification: "hey, two things need you today — rent and thesis draft." Not two separate pings.

**Only for hard deadlines within 24 hours.** The notification fires because something with real external consequences is imminent. Not because the AI thinks you should "check in." Not because you haven't opened the app. Not because a soft task has been sitting too long.

**Everything else waits for presence.** When the user opens the app, the AI can say "a few things have been piling up" — but that's inside the chat, not as a push notification. The user chose to open the app, so they have bandwidth. A push notification is an interruption they didn't choose.

**Days of silence is fine.** If the user hasn't dumped anything with hard deadlines, the app sends zero notifications. Days can pass in silence. That's the product working correctly, not a broken engagement loop.

**No manipulation tactics.** No "you haven't checked in today." No streaks. No "your productivity score dropped." No badge counts on the app icon. These are designed to create anxiety that drives opens. We want the opposite: the user opens the app because it helps them, not because it guilts them.

### The goal

The user should develop a Pavlovian response: "when this app pings me, it actually matters." One notification = one genuinely important thing. That trust is more valuable than any engagement metric.

---

## Platform Strategy

### PWA (Progressive Web App)

The product ships as a Progressive Web App — a web application that installs to the phone's home screen, gets its own icon, opens fullscreen without browser chrome, and supports push notifications. To the user, it feels like a native app. Technically, it's one codebase that works everywhere.

### Why PWA

**For the user:** Go to a URL → "Add to home screen" → done. No app store search, no download wait, no account creation screen, no permissions dialog parade. The install friction is as close to zero as possible.

**For distribution:** No app store review process (ship updates instantly), no 15-30% app store tax on subscriptions, no platform-specific builds to maintain.

**For development speed:** One codebase. Ships in days, not weeks. Can be wrapped in a native shell later (Capacitor, etc.) for app store distribution if needed.

### The "one surface" principle

The product exists in exactly one place: the PWA on your home screen. Not a PWA AND a Telegram bot AND a desktop app. Every additional surface is another decision ("where did I tell it about that thing?") and another thing to maintain — both for the developer and the user.

If someone wants to use it on desktop, it's the same URL in a browser tab. Same data, same chat, same everything. No sync issues because there's nothing to sync.

### Push notifications via PWA

Modern PWAs support push notifications on iOS (since iOS 16.4), Android, and desktop. This covers the "one notification per day for hard deadlines" requirement without needing a native app. The user grants notification permission once during install — one decision, then never asked again.

---

## Pricing

### The core constraint

Every message costs money — the AI backend (LLM API calls) has per-token costs. A one-time purchase doesn't work when the ongoing cost scales with usage. Subscription is the only sustainable model.

### The ADHD pricing problem

An ADHD person staring at three plan tiers with a feature comparison table will close the tab. That's another decision matrix, another "which one is right for me?" moment, another spoon spent before they even try the product. Tiered pricing is a conversion killer for this audience.

### The solution: one price, no tiers

**Free tier:** Full functionality, rate-limited to ~10 messages per day. Not a crippled "lite" version — the same product, just with a daily cap. Enough to be genuinely useful and build the habit. No feature gating. Reminders work. "What should I do?" works. Everything works.

**Paid tier: $8/month.** Unlimited messages. That's it. One price. No "Pro" vs "Premium" vs "Enterprise." No annual vs monthly decision. No feature unlocks — just the rate limit removed.

### Why $8

It's below the "do I need to think about this?" threshold for most working adults and students. It's a coffee and a half. Less than Spotify. Less than every competitor: Motion ($19-29), alfred_ ($25), Saner.AI Standard ($16). It's impulse-affordable.

For unit economics: if a paid user sends ~30 messages per day, each requiring one LLM call, that's roughly $1-3/month in API costs depending on the model and prompt length. Healthy margin at $8.

### How the upgrade works

No pricing page. No plan comparison. When you hit the daily free limit, one message appears in the chat: "I'm out of messages for today. Unlimited is $8/month — want me to set that up?" One tap. Done. Cancellation works the same way: type "cancel subscription" in the chat and it's handled. No settings page to find, no "manage subscription" buried in a menu.

### Why not freemium with feature gating

Feature gating means the free user gets a worse product. They think "this is okay but not great" and leave. With rate limiting instead, the free user gets the full experience 10 times a day. They think "this is great, I just want more of it." That's a much stronger upgrade motivation — you're not selling them features they haven't tried, you're removing a limit on something they already love.

---

## Success Metrics (v0.1)

Since this is a personal dogfood first, success is simple:

- **Am I still using it after 2 weeks?** If yes, the core loop works.
- **Am I capturing things I would have otherwise forgotten?** If yes, the zero-friction capture works.
- **Am I doing more things on time?** If yes, the nudging works.
- **Do I dread opening it?** If no, the anti-accumulation design works.

---

## Tech Stack (Locked)

### System Architecture

```
Browser (PWA)  ←→  CDN (Vercel/Cloudflare Pages — static files, free)
     │
     ▼ HTTPS
Single FastAPI server
  ├── /api/*    ← user requests (chat, auth, history, payment)
  └── /jobs/*   ← QStash cron calls (deadlines, urgency, calendar sync, patterns)
     │
     ├── Supabase (Postgres + pgvector + Auth)
     ├── Upstash Redis (session cache)
     ├── Upstash QStash (cron + job queue)
     ├── LLM API (Claude/OpenAI)
     ├── Google Calendar API (read-only)
     └── Stripe (payments)
```

Frontend and backend are separate codebases but the backend is ONE server. Route groups (/api/* and /jobs/*) are logically separated in code/directories but deployed as a single process. Split into separate services only when scale demands it.

### Existing Infrastructure (konf-dev)

The product is built on top of an existing agentic AI platform. These components are vibe-coded but architecturally sound — to be hardened post-MVP.

**Sutra** — Declarative YAML-based AI agent orchestration (Python). Provider-agnostic, parallel execution, built on LangGraph. NOT used in v0.1 — the orchestrator is plain FastAPI. Sutra becomes the orchestration layer when the monolithic LLM call needs to be decomposed into separate pipeline stages.

**Konf-Tools** — Standardized tool execution API (FastAPI). Provides HTTP requests, storage, memory operations, and audit logging with namespace isolation. Available for future integrations.

**Smrti** — Multi-tier memory storage system (Python/FastAPI). 5 memory tiers with protocol-based pluggable adapters, multi-tenant namespace isolation, async-first, Prometheus metrics. This is the memory backbone.

### Managed Services (zero infrastructure to maintain)

| Service | Role | Free Tier | Paid |
|---|---|---|---|
| **Supabase** | PostgreSQL + pgvector + Auth | 500MB DB, 50K MAU | $25/month |
| **Upstash Redis** | Session cache (WORKING + SHORT_TERM) | 500K commands/month | ~$10/month |
| **Upstash QStash** | Cron jobs + async job queue | 500 messages/day | ~$10/month |
| **Vercel** or **Cloudflare Pages** | PWA static hosting | Generous free | Free for this scale |
| **Stripe** | Subscription payments | No monthly fee | 2.9% + 30¢ per transaction |
| **Google Cloud** | OAuth + Calendar API | Free (calendar API free tier) | Free at this scale |

### Backend Deployment: Railway

FastAPI server deployed on **Railway**. Push to GitHub → auto-deploys. Zero server management.

What Railway provides: automatic HTTPS/SSL, custom domain support (`api.unspool.life`), environment variables dashboard, instant rollbacks, PR preview deployments, branch-based environment mapping (`main` → production, `develop` → staging), horizontal + vertical scaling, and usage-based pricing (~$5-10/month at MVP scale).

What Railway does NOT provide: automated test running (add GitHub Actions for `pytest` if needed — Railway deploys after CI passes).

Setup: one Railway project, one service (FastAPI), two environments (staging + production). Databases are external (Supabase + Upstash), not Railway-managed.

### Smrti Tier → Backend Mapping

| Smrti Tier | Purpose in Product | Backend | Managed By |
|---|---|---|---|
| **WORKING** (5min TTL) | Active session cache — assembled LLM context, conversation state | Redis | Upstash |
| **SHORT_TERM** (1hr TTL) | Session state — current mood/energy, items surfaced this session | Redis | Upstash |
| **EPISODIC** (persistent) | Raw conversation log — every message in/out, timestamped | PostgreSQL | Supabase |
| **SEMANTIC** (persistent) | Extracted facts — user profile, preferences, learned patterns | PostgreSQL | Supabase |
| **LONG_TERM** (persistent + vectors) | All stored items + ideas with embeddings for semantic search | PostgreSQL + pgvector | Supabase |

### Adapter Strategy

Smrti's protocol-based architecture means we write new adapters for managed backends while keeping the interface identical:

- `SupabasePostgresAdapter` → replaces self-hosted Postgres for EPISODIC + SEMANTIC tiers
- `PgvectorLongTermAdapter` → replaces Qdrant for LONG_TERM tier (embeddings in pgvector column)
- `UpstashRedisAdapter` → replaces self-hosted Redis for WORKING + SHORT_TERM tiers

The orchestrator never knows or cares what's behind the adapters. Backends are swappable without touching business logic.

### Context Intelligence

The "when to fetch what and when to save what" intelligence lives in the orchestrator (Sutra pipelines), not in the database layer. Smrti is intentionally a dumb storage layer. The orchestrator decides what context to load based on intent classification and assembles the LLM prompt accordingly.

Context fetching strategy will be determined during implementation — likely a combination of: lightweight LLM call to determine what context is needed, direct DB queries for known patterns (e.g., "items due < 48hrs" is always a SQL query, not a semantic search), and session caching to avoid redundant fetches during active chat.

### Frontend

PWA (Progressive Web App). Single-page chat interface. Installable to home screen, fullscreen, push notifications. One codebase for all devices. Convertible to native app later via Capacitor if needed (1-2 day effort).

### Cost at Scale

| Users | Supabase | Upstash | LLM API (~30 msgs/user/day) | Total |
|---|---|---|---|---|
| 1 (dogfood) | Free | Free | ~$2/month | ~$2/month |
| 50 (beta) | Free | Free | ~$75/month | ~$75/month |
| 500 (launch) | $25/month | $10/month | ~$750/month | ~$785/month |

At 500 users × $8/month subscription = $4,000/month revenue. Healthy margin from day one.

---

## Open Questions

- **~~What's the chat platform for v0.1?~~** → Resolved: PWA.
- **~~Monetization?~~** → Resolved: Free (10 msgs/day, full features) + $8/month unlimited. No tiers.
- **~~Database/infra?~~** → Resolved: Supabase (Postgres + pgvector + auth) + Upstash Redis. Zero self-hosted infra.
- **~~Name?~~** → Resolved: **Unspool** — unspool.life
- **~~Voice input?~~** → Resolved: In v0.1. Web Speech API with swappable provider interface. Transcript appears in input for review before sending.
- **~~Auth for v0.1?~~** → Resolved: Both from day one. Google Sign-In as primary (includes calendar.readonly scope in one consent screen). Magic link as fallback. Supabase Auth handles both.
- **~~Calendar integration?~~** → Resolved: Google Calendar read-only, bundled with Google Sign-In. One consent screen, zero extra friction. Requires Google OAuth verification for public launch (100 test users allowed before verification).
- **~~UI approach?~~** → Resolved: Fullscreen dark chat, no navigation, no sidebar, no header. User messages right, AI messages left. Mic button swaps to send button on text input.
- **~~Backend orchestrator?~~** → Resolved: Plain FastAPI for v0.1 (single endpoint, monolithic LLM call). Migrate to Sutra pipelines when decomposition is needed.
- **Which LLM backend?** Claude API? OpenAI? Decision deferred — the product is model-agnostic. Likely a single medium model (Claude Sonnet or GPT-4o-mini) for v0.1 doing classification + extraction + response in one call.
- **Multi-user?** Smrti already supports namespace isolation, so multi-tenant is architecturally ready. Not prioritized for v0.1.

---

*This spec is the complete product definition for v0.1. Everything above the "MVP Scope" section is the long-term vision. Everything in the MVP section is what ships this weekend.*
