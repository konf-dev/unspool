# Unspool

An AI personal assistant for people with ADHD. One chat interface — brain-dump tasks, ideas, deadlines, and thoughts. The AI handles categorization, prioritization, and scheduling invisibly. No dashboards, no lists, no settings. Just talk.

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Set `VITE_USE_MOCKS=true` in `frontend/.env.development` to run the frontend without a backend.

Copy `.env.example` and fill in your keys — see [docs/DEPLOY.md](docs/DEPLOY.md) for where to get each one.

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | React 19 + Vite 6 + Tailwind 4 + Zustand 5 + Framer Motion 12 (PWA) → Vercel |
| Backend | Python 3.11+ / FastAPI / async → Railway |
| Database | Supabase (Postgres + pgvector + Auth) |
| Cache | Upstash Redis |
| Jobs | Upstash QStash (cron + delayed queue) |
| LLM | Google Gemini (chat, extraction, embeddings) |

## Repo Structure

```
unspool/
├── frontend/              # React 19 PWA — "Midnight Sanctuary" design system
│   ├── src/
│   │   ├── components/    # stream/, plate/, landing/, auth/, legal/, shared/, system/
│   │   ├── stores/        # Zustand: auth, message, plate, ui
│   │   ├── hooks/         # useAuth, useChat, useVoice, usePush, useScrollAnchor, ...
│   │   ├── lib/           # API client (SSE), Supabase, action parser
│   │   ├── styles/        # Tailwind globals + animations
│   │   └── types/         # TypeScript types + env declarations
│   ├── test/              # Vitest unit tests + MSW mocks
│   ├── e2e/               # Playwright E2E tests
│   └── package.json
├── backend/
│   ├── config/            # YAML config (proactive triggers, scoring, jobs)
│   ├── prompts/           # Jinja2 prompt templates (first-person voice)
│   ├── src/               # FastAPI app
│   │   ├── api/           # User-facing endpoints (chat SSE, messages, push)
│   │   ├── agents/        # Hot path (LangGraph + Gemini) + Cold path (extraction)
│   │   ├── core/          # Graph ops, models, database, settings
│   │   ├── jobs/          # Background job endpoints (cron, synthesis)
│   │   ├── proactive/     # Proactive message engine + evaluators
│   │   ├── integrations/  # Gemini, QStash, Redis, Push
│   │   └── db/            # Queries, Redis client
│   ├── supabase/          # Migrations
│   └── requirements.txt
├── scripts/               # Operational scripts (migrate.sh, diagnose.sh)
├── docs/                  # Detailed specs and guides
└── archive/               # V1 frontend (reference)
```

## Documentation

- [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) — Product specification
- [docs/FRONTEND_SPEC.md](docs/FRONTEND_SPEC.md) — Frontend specification (Midnight Sanctuary)
- [docs/MEMORY_ARCHITECTURE.md](docs/MEMORY_ARCHITECTURE.md) — Memory system design
- [docs/CHAT_INTERACTIONS.md](docs/CHAT_INTERACTIONS.md) — Interaction pattern examples
- [docs/DEPLOY.md](docs/DEPLOY.md) — Deployment guide (initial setup)
- [docs/v2/](docs/v2/README.md) — V2 backend docs (architecture, API, agent design, database, auth, telemetry)
- [docs/v2/deployment.md](docs/v2/deployment.md) — Ongoing deployment & migration protocol

## Tests

```bash
# Backend unit tests
cd backend && pytest -v

# Frontend (17 unit + 14 E2E + type check + build)
cd frontend && npm test && npx tsc --noEmit && npm run build
cd frontend && npx playwright test
```

## Database Migrations

Migrations are tracked via `schema_migrations` and applied with the runner:

```bash
./scripts/migrate.sh --status     # See what's applied/pending
./scripts/migrate.sh --dry-run    # Preview changes
./scripts/migrate.sh              # Backup + apply
```

See [docs/v2/deployment.md](docs/v2/deployment.md#migration-protocol) for the full protocol.

## License

All rights reserved.
