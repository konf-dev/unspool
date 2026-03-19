# CLAUDE.md — Unspool Project Context

## What is Unspool?

Unspool (unspool.life) is an AI personal assistant for people who are overwhelmed. It's a single chat interface where users brain-dump tasks, ideas, deadlines, and random thoughts. The AI handles all categorization, prioritization, and scheduling invisibly. No dashboards, no lists, no settings. Just a chat box.

**One-line pitch:** An AI that remembers everything so you don't have to. No app to organize. No inbox to clear. Just talk.

**Voice:** First-person — "your own mind, but reliable." Not a chatbot talking TO you, but your thoughts externalized. This is the positioning moat.

**Never mention ADHD in the product itself.** Lead with the problem: "Every productivity app charges you an invisible tax: decisions. Unspool doesn't."

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

## Architecture Status

> **Current state:** The backend uses a config-driven pipeline orchestrator (YAML pipelines + Jinja2 prompts + intent classification). This is being rearchitected to a **single-LLM tool-calling agent** with graph memory. The current pipeline code is still running in production until the new architecture is implemented. See `docs/LLM_AGENT_RESEARCH.md` for the research behind this decision.

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
- **Streaming:** SSE for token-by-token AI responses
- **Voice:** Web Speech API with swappable provider interface

### Backend (this repo: /backend)
- **Stack:** Python 3.11+ / FastAPI / async
- **Deployed to:** Railway (auto-deploy from main branch)
- **LLM:** OpenAI (gpt-4.1 for responses, gpt-4.1-nano for classification)
- **Storage:** Direct async calls to Supabase (Postgres/pgvector) + Upstash (Redis). No abstraction layer.
- **Background jobs:** FastAPI endpoints called by Upstash QStash on schedule
- **Graph memory:** Fully implemented node/edge graph with trigger-based retrieval (currently in shadow mode)

### Database
- **Every table must have RLS enabled.** Supabase auto-enables it. Write policies for user_id scoping.
- **Items table uses pgvector column** for embeddings (text-embedding-3-small, 1536 dims). Embeddings generated in post-conversation background job, not in request path.
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
- **FastAPI dependency mocking:** Use `app.dependency_overrides[dep_fn] = lambda: value`, not `patch()`.
- **Langfuse instrumentation:** When adding `@observe` to a function that makes LLM calls, also call `update_current_observation(model=..., input=..., output=..., usage=...)` to report the actual LLM data.
- **Test file naming:** One test file per source module: `test_<module>.py`. Tests live flat in `backend/tests/`. Test functions: `test_<what_it_tests>`.
- **SQL migrations:** Sequential numbering `00NNN_<description>.sql` in `backend/supabase/migrations/`. Always include `IF NOT EXISTS` / `IF EXISTS` guards.

### TypeScript (frontend)
- **Functional components only.** No class components.
- **Named exports.** No default exports except for pages/screens.
- **No `any` type.** Type everything.
- **CSS variables** for all colors and spacing (defined in globals.css).
- **No CSS-in-JS libraries.** Plain CSS or CSS modules.
- Prettier for formatting.

### Error Handling
- **The user must always get a response.** No matter what breaks — LLM timeout, DB down, tool crash — the chat endpoint must send an error message via SSE, never hang or return a 500.
- **Fail open on non-critical services.** Redis down → skip rate limiting. Optional fields fail → log warning and continue.
- **Never crash the server process.** Background jobs must catch their own exceptions internally.
- **60-second timeout.** If anything hangs, user gets a timeout message instead of infinite spinner.
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

- `docs/PRODUCT_SPEC.md` — Full product specification, pricing, tech stack
- `docs/CHAT_INTERACTIONS.md` — Example conversation flows (the product bible)
- `docs/FRONTEND_SPEC.md` — Detailed UI/UX spec with platform compatibility notes
- `docs/SCHEMA.md` — Database schema reference
- `docs/GRAPH_MEMORY.md` — Graph memory system: architecture, triggers, serialization
- `docs/LLM_AGENT_RESEARCH.md` — LLM model comparison, tool calling research, architecture patterns
- `docs/DEPLOY.md` — Infrastructure setup and deployment procedures
- `docs/OBSERVABILITY.md` — Admin API, Langfuse tracing, debugging workflows
- `docs/ROADMAP.md` — Phased roadmap with current status

## Git Rules

- **Always ask before pushing to remote or merging to main.** Never run `git push`, `git merge main`, or `gh pr merge` without explicit user confirmation. Commits are fine, pushing is not — pushing triggers production deployments.

## Post-Push Verification

After every push to `main`, verify the deployment succeeded. **All 4 steps are required:**

```bash
# 1. Check backend health
curl -s https://api.unspool.life/health | jq

# 2. Check for recent errors
curl -s -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/errors?limit=5 | jq

# 3. Check GitHub Actions CI status
gh run list --limit 3

# 4. Smoke test the chat endpoint
curl -s -X POST https://api.unspool.life/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hi","session_id":"smoke-test"}' \
  -w "\nHTTP %{http_code}\n" | tail -5
# Expected: 401 (Missing Bearer token)
```

## Debugging Production Issues

```bash
# Admin API
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/trace/{trace_id} | jq
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/user/{user_id}/messages | jq
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.unspool.life/admin/errors | jq

# Langfuse
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?limit=10" | jq

# Railway logs
railway logs

# GitHub Actions
gh run view --log-failed
```

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
