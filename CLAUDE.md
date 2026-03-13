# CLAUDE.md — Unspool Project Context

## What is Unspool?

Unspool (unspool.life) is an AI personal assistant for people with ADHD. It's a single chat interface where users brain-dump tasks, ideas, deadlines, and random thoughts. The AI handles all categorization, prioritization, and scheduling invisibly. No dashboards, no lists, no settings. Just a chat box.

**One-line pitch:** An AI that remembers everything so you don't have to. No app to organize. No inbox to clear. Just talk.

## Core Design Principles (non-negotiable)

1. **Zero decisions at capture.** User types. That's it. No categories, no priority levels, no "which project?" prompts.
2. **One thing at a time.** When user asks "what should I do?" — return ONE item, not a list. Lists are the enemy.
3. **No accumulation.** User never sees a growing backlog, badge counts, or overdue markers. Things that become irrelevant fade silently.
4. **No clock assumptions.** Product works for someone who wakes at 6am and someone who wakes at 3pm. No "plan your morning" flows.
5. **Presence-triggered.** AI activates when user shows up, not on a schedule.
6. **Gets smarter, not heavier.** More use = better understanding. More use ≠ more things to maintain.
7. **Setup is nothing.** First interaction is typing a message. No onboarding wizard.
8. **Quiet respect.** Max 1 push notification per day. No re-engagement manipulation. Silence is fine.
9. **One price, no decisions.** Free (10 msgs/day) + $8/month unlimited. No tiers.

## Architecture

```
Browser (PWA)  ←→  Vercel (static files)
     │
     ▼ HTTPS
Single FastAPI server (Railway)
  ├── /api/*    ← user requests (chat, auth, history)
  └── /jobs/*   ← Upstash QStash cron calls
     │
     ├── Supabase (Postgres + pgvector + Auth)
     ├── Upstash Redis (session cache)
     ├── Upstash QStash (cron + job queue)
     ├── LLM API (TBD — Claude or OpenAI)
     ├── Google Calendar API (read-only)
     └── Stripe (payments, post-MVP)
```

### Frontend (this repo: /frontend)
- **Stack:** React + Vite + TypeScript
- **Output:** PWA deployed to Vercel
- **UI:** Single fullscreen dark chat interface. Nothing else.
- **Auth:** Supabase JS SDK — Google OAuth (primary) + magic link (fallback)
- **Streaming:** SSE or fetch ReadableStream for token-by-token AI responses
- **Voice:** Web Speech API with swappable provider interface

### Backend (this repo: /backend)
- **Stack:** Python 3.11+ / FastAPI / async
- **Deployed to:** Railway (auto-deploy from main branch)
- **Orchestrator:** Config-driven engine — YAML pipelines + Jinja2 prompts + registered tools
- **Storage:** Direct async calls to Supabase (Postgres/pgvector) + Upstash (Redis). No abstraction layer.
- **Background jobs:** FastAPI endpoints called by Upstash QStash on schedule

### Shared infra (external services, not in this repo)
- **Supabase:** Postgres + pgvector + Auth (Google OAuth + magic link)
- **Upstash Redis:** WORKING tier (5min TTL) + SHORT_TERM tier (1hr TTL)
- **Upstash QStash:** Cron scheduler calling /jobs/* endpoints

## Repo Structure

```
unspool/
├── CLAUDE.md              # This file
├── README.md
├── docs/
│   ├── PRODUCT_SPEC.md    # Full product specification
│   ├── ORCHESTRATOR_FLOW.md # Message processing pipeline
│   ├── ORCHESTRATOR_FLOW.md # Message processing pipeline
│   ├── FRONTEND_SPEC.md   # Detailed frontend specification
│   ├── SCHEMA.md          # Database schema reference
│   ├── PIPELINE_FORMAT.md # Pipeline YAML format spec
│   ├── DEPLOY.md          # Deployment guide
│   └── TOOLS.md           # Tool registry reference
├── frontend/              # React + Vite PWA
│   ├── public/
│   │   ├── fonts/         # Satoshi Variable (self-hosted woff2)
│   │   └── icons/         # PWA icons (SVG)
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/    # LoginScreen, ChatScreen, MessageList,
│   │   │                  # MessageBubble, ActionButtons, InputBar,
│   │   │                  # VoiceInput, TypingIndicator, StreamingText,
│   │   │                  # PaymentPrompt, CatEasterEgg, OfflineBanner
│   │   ├── hooks/         # useAuth, useVoice, usePush, useOffline,
│   │   │                  # useCatEasterEgg
│   │   ├── lib/           # api.ts, mock.ts, supabase.ts, constants.ts
│   │   ├── styles/        # globals.css, stars.css
│   │   └── types/         # index.ts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/
│   ├── config/
│   │   ├── pipelines/     # 10 YAML pipeline definitions
│   │   ├── intents.yaml   # Intent taxonomy + pipeline routing
│   │   ├── context_rules.yaml  # Per-intent data loading rules
│   │   ├── scoring.yaml   # All thresholds: urgency, decay, energy,
│   │   │                  # momentum, pick_next, reschedule, matching,
│   │   │                  # notifications
│   │   ├── proactive.yaml # Proactive message trigger rules
│   │   ├── gate.yaml      # Rate limits (free/paid)
│   │   └── variants.yaml  # A/B test definitions
│   ├── prompts/           # 21 Jinja2 prompt templates (.md)
│   ├── supabase/
│   │   └── migrations/    # SQL schema migrations
│   ├── src/
│   │   ├── main.py        # FastAPI app entry
│   │   ├── config.py      # Settings from env vars
│   │   ├── api/           # chat.py, messages.py, subscribe.py, auth_token.py
│   │   ├── jobs/          # check_deadlines, decay_urgency, process_conversation,
│   │   │                  # sync_calendar, detect_patterns
│   │   ├── orchestrator/  # engine.py, intent.py, context.py, config_loader.py,
│   │   │                  # prompt_renderer.py, variant_selector.py, types.py
│   │   ├── tools/         # registry.py, db_tools.py, scoring_tools.py,
│   │   │                  # context_tools.py, item_matching.py, momentum_tools.py
│   │   ├── llm/           # protocol.py, anthropic_provider.py, openai_provider.py,
│   │   │                  # embedding.py, registry.py
│   │   ├── db/            # supabase.py (asyncpg), redis.py (Upstash)
│   │   ├── integrations/  # google_calendar.py, stripe.py, push.py
│   │   ├── auth/          # supabase_auth.py, qstash_auth.py
│   │   └── telemetry/     # logger.py, events.py, middleware.py
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.json
└── .env.example
```

## Key Technical Decisions

### Frontend
- **Dark theme only.** No light mode in v0.1. Background: #0D0D0F (warm dark gray, not pure black).
- **No component library.** Custom chat components — they're simple enough.
- **No state management library.** React useState/useContext only. ~7 pieces of state total.
- **Font:** NOT Inter, NOT Roboto, NOT system default. Choose Satoshi, General Sans, Switzer, or Cabinet Grotesk.
- **Accent color:** Muted teal or dusty sage. NOT blue (every app is blue).
- **100dvh not 100vh.** Mobile Safari viewport fix.
- **16px minimum font on inputs.** Prevents iOS auto-zoom.
- **overscroll-behavior: none** on message container. Prevents rubber-band bounce.
- **env(safe-area-inset-bottom)** on input bar. iPhone notch/home bar.

### Backend
- **v0.1 is a monolith.** One FastAPI process handles /api/* and /jobs/*. Split later if needed.
- **Orchestrator is config-driven.** Three layers: config (YAML pipelines, prompts, scoring) / engine (~400 lines, never changes) / tools (Python functions). Adding new behavior = config change.
- **Intent classification is LLM-only.** Every message goes through the classify_intent prompt. No hardcoded regex patterns — avoids misclassification on ambiguous inputs.
- **Target: 1-2 LLM calls per user message.** Classification + extraction + response can often be one structured call.
- **All /jobs/* endpoints verify Upstash-Signature header.** Prevents external triggering.
- **All /api/* endpoints verify Supabase JWT.** Extract user_id from token.

### Database
- **Every table must have RLS enabled.** Supabase auto-enables it. Write policies for user_id scoping.
- **Items table uses pgvector column** for embeddings. Embeddings generated in post-conversation background job, not in request path.
- **No category field, no project field, no tags.** The data model intentionally excludes these.

## Data Model

### items table
```sql
CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  raw_text TEXT NOT NULL,
  interpreted_action TEXT NOT NULL,
  deadline_type TEXT CHECK (deadline_type IN ('hard', 'soft', 'none')),
  deadline_at TIMESTAMPTZ,
  urgency_score FLOAT DEFAULT 0.0,
  energy_estimate TEXT CHECK (energy_estimate IN ('low', 'medium', 'high')),
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'done', 'expired', 'deprioritized')),
  created_at TIMESTAMPTZ DEFAULT now(),
  last_surfaced_at TIMESTAMPTZ,
  nudge_after TIMESTAMPTZ,
  embedding vector(1536)
);

-- RLS policy
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own items" ON items
  FOR ALL USING (auth.uid() = user_id);
```

### messages table
```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  metadata JSONB DEFAULT '{}'
);

-- RLS policy
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own messages" ON messages
  FOR ALL USING (auth.uid() = user_id);
```

### user_profiles table
```sql
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  display_name TEXT,
  timezone TEXT,
  tone_preference TEXT DEFAULT 'casual',
  length_preference TEXT DEFAULT 'medium',
  pushiness_preference TEXT DEFAULT 'gentle',
  uses_emoji BOOLEAN DEFAULT false,
  primary_language TEXT DEFAULT 'en',
  google_calendar_connected BOOLEAN DEFAULT false,
  notification_sent_today BOOLEAN DEFAULT false,
  last_interaction_at TIMESTAMPTZ,
  patterns JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own profile" ON user_profiles
  FOR ALL USING (auth.uid() = id);
```

## Background Jobs

| Job | Endpoint | Schedule | What it does |
|---|---|---|---|
| Deadline scanner | POST /jobs/check-deadlines | Hourly | Send push for hard deadlines <24h away |
| Urgency decay | POST /jobs/decay-urgency | Every 6h | Recalculate urgency scores, expire old items |
| Process conversation | POST /jobs/process-conversation | After each chat (delayed 10s) | Embeddings, dedup, profile extraction |
| Calendar sync | POST /jobs/sync-calendar | Every 4h | Fetch Google Calendar events |
| Pattern detection | POST /jobs/detect-patterns | Daily | Analyze behavior, update personalization |

## Environment Variables

```bash
# Supabase
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
SUPABASE_JWT_SIGNING_SECRET=

# Upstash Redis
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# Upstash QStash
QSTASH_TOKEN=
QSTASH_CURRENT_SIGNING_KEY=
QSTASH_NEXT_SIGNING_KEY=

# Google OAuth (also configured in Supabase dashboard)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# LLM
LLM_API_KEY=
LLM_MODEL=

# App
ENVIRONMENT=development
FRONTEND_URL=http://localhost:5173
API_URL=http://localhost:8000
```

## Coding Conventions

### Python (backend)
- **Async everywhere.** All route handlers are `async def`. All DB calls use async clients.
- **Type hints required** on all function signatures.
- **Pydantic models** for all request/response schemas.
- **No print statements.** Use `structlog` for logging.
- **Black** for formatting (line length 100).
- **Ruff** for linting.
- Tests in `/backend/tests/` using pytest + pytest-asyncio.

### TypeScript (frontend)
- **Functional components only.** No class components.
- **Named exports.** No default exports except for pages/screens.
- **No `any` type.** Type everything.
- **CSS variables** for all colors and spacing (defined in globals.css).
- **No CSS-in-JS libraries.** Plain CSS or CSS modules.
- Prettier for formatting.

### General
- **No comments explaining what code does.** Code should be self-documenting. Comments only for WHY something is non-obvious.
- **Small files.** Each file does one thing. If a file exceeds ~200 lines, split it.
- **No premature abstraction.** Write it inline first, extract when you see the pattern repeat 3+ times.

## What NOT to Build

- No dashboard, settings page, or admin panel
- No categories, tags, projects, or folders — not even in the backend
- No daily/weekly review flows
- No streaks, gamification, or achievement systems
- No "you haven't checked in today" re-engagement
- No light mode (v0.1)
- No Apple/Outlook calendar (v0.1, Google only)
- No email integration (v0.1)

## Reference Docs

Read these before making architectural decisions:
- `docs/PRODUCT_SPEC.md` — Full product specification, pricing, tech stack
- `docs/ORCHESTRATOR_FLOW.md` — Every message processing path
- `docs/FRONTEND_SPEC.md` — Detailed UI/UX spec with platform compatibility notes

## Quick Commands

```bash
# Frontend
cd frontend && npm install && npm run dev    # Dev server at localhost:5173

# Backend
cd backend && pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000    # Dev server at localhost:8000

# Tests
cd backend && pytest
cd frontend && npm run test
```
