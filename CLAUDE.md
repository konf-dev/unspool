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
     ├── LLM API (OpenAI primary, Anthropic available)
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
│   ├── FRONTEND_SPEC.md   # Detailed frontend specification
│   ├── SCHEMA.md          # Database schema reference
│   ├── PIPELINE_FORMAT.md # Pipeline YAML format spec
│   ├── CONFIG_MAP.md      # Config file relationships and flow
│   ├── CHAT_INTERACTIONS.md # Example conversation flows
│   ├── DEPLOY.md          # Deployment guide
│   ├── DEPLOYMENT_LOG.md  # Exact steps followed, issues hit, current state
│   ├── OBSERVABILITY.md   # Admin API, Langfuse, debugging guide
│   ├── TOOLS.md           # Tool registry reference
│   └── ROADMAP.md         # Phased roadmap (1.5 → 5)
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
│   │   ├── scoring.yaml   # Thresholds: decay, momentum, pick_next,
│   │   │                  # reschedule, matching, notifications
│   │   ├── proactive.yaml # Proactive message trigger rules
│   │   ├── gate.yaml      # Rate limits (free/paid)
│   │   ├── jobs.yaml      # Cron schedules + post-processing dispatch map
│   │   ├── patterns.yaml  # Pattern detection analysis definitions
│   │   ├── variants.yaml  # A/B test definitions
│   │   ├── graph.yaml     # Graph memory system config
│   │   └── triggers.yaml  # Graph retrieval trigger chain definitions
│   ├── prompts/           # 28 Jinja2 prompt templates (.md)
│   ├── supabase/
│   │   └── migrations/    # SQL schema (single 00001_full_schema.sql)
│   ├── src/
│   │   ├── main.py        # FastAPI app entry
│   │   ├── config.py      # Settings from env vars
│   │   ├── api/           # chat.py, messages.py, subscribe.py, auth_token.py,
│   │   │                  # admin.py
│   │   ├── graph/         # types.py, db.py, triggers.py, retrieval.py,
│   │   │                  # serialization.py, ingest.py, evolve.py, feedback.py
│   │   ├── jobs/          # check_deadlines, decay_urgency, process_conversation,
│   │   │                  # process_graph, sync_calendar, detect_patterns,
│   │   │                  # reset_notifications
│   │   ├── orchestrator/  # engine.py, intent.py, context.py, config_loader.py,
│   │   │                  # prompt_renderer.py, variant_selector.py, types.py
│   │   ├── tools/         # registry.py, db_tools.py, scoring_tools.py,
│   │   │                  # context_tools.py, graph_tools.py, item_matching.py,
│   │   │                  # momentum_tools.py, query_tools.py
│   │   ├── llm/           # protocol.py, anthropic_provider.py, openai_provider.py,
│   │   │                  # embedding.py, registry.py
│   │   ├── db/            # supabase.py (asyncpg), redis.py (Upstash async)
│   │   ├── integrations/  # google_calendar.py, stripe.py, push.py, qstash.py
│   │   ├── auth/          # supabase_auth.py, qstash_auth.py, admin_auth.py
│   │   └── telemetry/     # logger.py, events.py, middleware.py,
│   │                      # langfuse_integration.py
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
- **Font:** Satoshi Variable (self-hosted woff2). NOT Inter, NOT Roboto, NOT system default.
- **Accent color:** Muted teal or dusty sage. NOT blue (every app is blue).
- **100dvh not 100vh.** Mobile Safari viewport fix.
- **16px minimum font on inputs.** Prevents iOS auto-zoom.
- **overscroll-behavior: none** on message container. Prevents rubber-band bounce.
- **env(safe-area-inset-bottom)** on input bar. iPhone notch/home bar.

### Backend
- **v0.1 is a monolith.** One FastAPI process handles /api/* and /jobs/*. Split later if needed.
- **Orchestrator is config-driven.** Three layers: config (YAML pipelines, prompts, scoring) / engine (~400 lines, never changes) / tools (Python functions). Adding new behavior = config change.
- **Intent classification is LLM-only.** Every message goes through the classify_intent prompt. No hardcoded regex patterns — avoids misclassification on ambiguous inputs.
- **Energy and urgency are LLM-inferred.** No regex word-pattern matching. The LLM estimates energy_estimate and urgency_score in the extract prompt. `enrich_items` only fills defaults when the LLM returns null.
- **System prompt injected into all pipeline LLM calls.** `prompts/system.md` provides consistent Unspool personality and user preferences across all pipelines.
- **Target: 1-2 LLM calls per user message.** Classification + extraction + response can often be one structured call. Query searches use 2 (analyze + respond).
- **All /jobs/* endpoints verify Upstash-Signature header.** Prevents external triggering.
- **Post-processing dispatched via QStash.** Pipeline YAML defines `post_processing` jobs; `chat.py` dispatches them after saving the assistant response.
- **60-second pipeline timeout.** If the LLM hangs or a tool stalls, the user gets "sorry, that took too long" instead of infinite spinner. Pipeline crashes show "sorry, something went wrong." Both are saved with `metadata.error=true`.
- **Graceful degradation.** Redis down → rate limiting skipped (fail open). LLM API down → falls back to conversation intent. Individual tool/step failures are logged but don't crash the pipeline when possible.
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
| Process conversation | POST /jobs/process-conversation | After each chat (delayed 10s) | Embeddings, entity extraction, memory extraction |
| Process graph | POST /jobs/process-graph | After each chat (delayed 5s) | Graph node/edge ingest, embedding, feedback |
| Calendar sync | POST /jobs/sync-calendar | Every 4h | Fetch Google Calendar events |
| Pattern detection | POST /jobs/detect-patterns | Daily | Config-driven LLM analyses (behavioral, preferences) |
| Notification reset | POST /jobs/reset-notifications | Daily midnight | Reset notification_sent_today flag |

Cron schedules are defined in `config/jobs.yaml` and registered with QStash on production startup. Pattern detection analyses are defined in `config/patterns.yaml`.

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
LLM_MODEL=          # Default response model (gpt-4.1)
LLM_MODEL_FAST=     # Fast classification model (gpt-4.1-nano)

# Admin & Observability
ADMIN_API_KEY=
LANGFUSE_HOST=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# App
ENVIRONMENT=development
FRONTEND_URL=http://localhost:5173
API_URL=http://localhost:8000
```

## Coding Conventions

### Python (backend)
- **Async everywhere.** All route handlers are `async def`. All DB calls use async clients.
- **Type hints required** on all function signatures. Never use string-quoted annotations (`"SomeType"`) — import the type and use it directly.
- **Pydantic models** for all request/response schemas.
- **No print statements.** Use `structlog` for logging.
- **Ruff** for both formatting and linting. Run `ruff format .` and `ruff check .` before committing. CI enforces both.
- Tests in `/backend/tests/` using pytest + pytest-asyncio. Always run full suite (`pytest -x --timeout=30`) before pushing.
- **FastAPI dependency mocking:** Use `app.dependency_overrides[dep_fn] = lambda: value`, not `patch()`. FastAPI resolves deps via its own DI, not Python imports.
- **Multiple context managers from a list:** Use `contextlib.ExitStack`, not `with (*list)` — tuple unpacking doesn't work in `with` statements.
- **Langfuse instrumentation:** When adding `@observe` to a function that makes LLM calls, also call `update_current_observation(model=..., input=..., output=..., usage=...)` to report the actual LLM data. The decorator alone only captures timing.
- **Test data shapes:** When testing Jinja2 templates, use realistic data that matches actual pipeline output shapes. Empty dicts/lists miss collisions like `results.items` (dict method vs data key).
- **Test file naming:** One test file per source module: `test_<module>.py`. Tests live flat in `backend/tests/` (no subdirectories). Test functions: `test_<what_it_tests>`.
- **Test fixtures:** Shared fixtures go in `conftest.py`. Use `app.dependency_overrides` for FastAPI deps, not `unittest.mock.patch`.
- **SQL migrations:** Sequential numbering `00NNN_<description>.sql` in `backend/supabase/migrations/`. Always include `IF NOT EXISTS` / `IF EXISTS` guards so migrations are idempotent. Never modify an existing migration file — always create a new one.

### TypeScript (frontend)
- **Functional components only.** No class components.
- **Named exports.** No default exports except for pages/screens.
- **No `any` type.** Type everything.
- **CSS variables** for all colors and spacing (defined in globals.css).
- **No CSS-in-JS libraries.** Plain CSS or CSS modules.
- Prettier for formatting.

### Error Handling
- **The user must always get a response.** No matter what breaks — LLM timeout, DB down, tool crash, bad JSON — the chat endpoint must send an error message via SSE, never hang or return a 500. The pattern: `wrapped_stream()` in `chat.py` catches `TimeoutError` and `Exception`, sends "sorry, something went wrong" as a token event, and saves it with `metadata.error=true`.
- **Fail open on non-critical services.** Redis down → skip rate limiting. Optional context fields fail → log warning and continue. Individual tool/step failures are logged but don't crash the pipeline when the step isn't required for the response.
- **Never crash the server process.** Background jobs (`/jobs/*`) must catch their own exceptions internally. A failing cron job should return an error dict, not take down the worker.
- **60-second pipeline timeout.** `asyncio.timeout()` wraps the entire pipeline (classify + assemble + execute). If anything hangs, user gets a timeout message instead of infinite spinner.
- **Log everything with trace_id.** Every error log must include `trace_id` so failures can be traced across Railway logs, Langfuse, and the admin API.

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
- `docs/PIPELINE_FORMAT.md` — Pipeline YAML format spec (read before adding/editing pipelines)
- `docs/CONFIG_MAP.md` — How config files relate to each other and the engine
- `docs/TOOLS.md` — Tool registry reference (read before adding tools)
- `docs/SCHEMA.md` — Database schema reference (read before writing migrations)
- `docs/DEPLOY.md` — Infrastructure setup and deployment procedures
- `docs/OBSERVABILITY.md` — Admin API, Langfuse tracing, debugging workflows
- `docs/DEPLOYMENT_LOG.md` — Exact steps followed, issues hit, and current production state
- `docs/ROADMAP.md` — Phased roadmap with current status of all work items
- `docs/GRAPH_MEMORY.md` — Graph memory system: architecture, triggers, serialization, going-live checklist

## Parallel Workstreams

Multiple Claude sessions may work on different roadmap items simultaneously. Follow these rules to avoid conflicts:

- **Always work on a feature branch.** Never commit directly to `main`. Branch naming: `<phase>/<short-description>` (e.g., `2a/prompt-injection`, `2b/pick-next-tests`, `2c/stripe-checkout`).
- **Keep changes scoped.** Only modify files directly related to your task. If you notice an unrelated issue, note it in a commit message or comment — don't fix it in your branch.
- **Shared files require extra care.** These files are touched by many features — minimize changes and keep diffs small:
  - `backend/src/main.py` — only add routes/middleware, don't restructure
  - `backend/src/api/chat.py` — the SSE pipeline, changes here affect everything
  - `backend/src/orchestrator/engine.py` — the core engine, rarely needs changes
  - `backend/src/config.py` — env vars, only add new ones
  - `frontend/src/App.tsx` — top-level routing
- **One migration per branch.** If your feature needs schema changes, create exactly one migration file. Never modify existing migration files.
- **Run the full test suite before committing.** `cd backend && pytest -x --timeout=30`. If tests fail, fix them — don't skip them.
- **Run ruff before committing.** `cd backend && ruff check . && ruff format .`

## Git Rules

- **Always ask before pushing to remote or merging to main.** Never run `git push`, `git merge main`, or `gh pr merge` without explicit user confirmation. Commits are fine, pushing is not — pushing triggers production deployments.

## Post-Push Verification

After every push to `main`, verify the deployment succeeded. **All 4 steps are required** — a passing health check does NOT mean the app works (e.g., rate limiting can silently block all users while health returns 200).

```bash
# 1. Check backend health (Railway auto-deploys, ~1-2 min)
curl -s https://api.unspool.life/health | jq

# 2. Check for recent errors
curl -s -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/errors?limit=5 | jq

# 3. Check GitHub Actions CI status
gh run list --limit 3

# 4. Smoke test the chat endpoint (catches auth, rate limiting, pipeline errors)
curl -s -X POST https://api.unspool.life/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hi","session_id":"smoke-test"}' \
  -w "\nHTTP %{http_code}\n" | tail -5
# Expected: 401 (Missing Bearer token) — proves the endpoint is reachable and FastAPI is routing.
# If you get 429, rate limiting is too aggressive. Check gate.yaml + Redis state.
# If you get 500, check Railway logs: railway logs | tail -30
```

If the health check fails or returns errors, check Railway logs for crash details. Vercel auto-deploys the frontend on push — it only needs checking if `frontend/` changed.

### Config change safety checklist

Before changing config values that affect live users (gate.yaml, scoring.yaml, proactive.yaml):
1. **Who is affected right now?** Check if the feature has dependencies that aren't live yet (e.g., lowering rate limits before Stripe is set up).
2. **Is there cached state?** Redis keys, session caches, and tier lookups may reflect old values. A config change doesn't reset them.
3. **Can you roll back?** Config changes deploy immediately on push. Know how to revert.

## Debugging Production Issues

You have CLI access to debug production without needing dashboards:

```bash
# Admin API — inspect traces, user data, errors
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/trace/{trace_id} | jq
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/user/{user_id}/messages | jq
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/errors | jq

# Langfuse — full LLM trace waterfall (prompts, responses, tokens, cost)
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?limit=10" | jq

# Railway logs
railway logs --filter "step.error"

# GitHub Actions
gh run view --log-failed
```

The trace_id from `X-Trace-Id` response header or `messages.metadata.trace_id` connects all three systems. See `docs/OBSERVABILITY.md` for detailed debugging workflows.

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

# Lint + format (run before committing)
cd backend && ruff check . && ruff format .
```
