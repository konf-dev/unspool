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
| LLM | Gemini (chat) + OpenAI (embeddings) |

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
│   ├── config/            # YAML pipelines, prompts, scoring rules
│   ├── prompts/           # Jinja2 prompt templates (first-person voice v2.1)
│   ├── src/               # FastAPI app
│   │   ├── api/           # User-facing endpoints (chat SSE, messages, push)
│   │   ├── jobs/          # Background job endpoints
│   │   ├── orchestrator/  # Config-driven message processing engine
│   │   ├── tools/         # Tool registry + implementations
│   │   ├── llm/           # LLM provider abstraction
│   │   └── db/            # Supabase + Redis clients
│   ├── tests/
│   └── requirements.txt
├── docs/                  # Detailed specs and guides
└── archive/               # V1 frontend (reference)
```

## Documentation

- [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) — Product specification
- [docs/FRONTEND_SPEC.md](docs/FRONTEND_SPEC.md) — Frontend V2 specification (Midnight Sanctuary)
- [docs/MEMORY_ARCHITECTURE.md](docs/MEMORY_ARCHITECTURE.md) — Memory system design
- [docs/CHAT_INTERACTIONS.md](docs/CHAT_INTERACTIONS.md) — Interaction pattern examples

## Tests

```bash
# Backend (103 tests)
cd backend && pytest -v

# Frontend (17 unit tests + type check + build)
cd frontend && npm test && npx tsc --noEmit && npm run build

# Frontend E2E
cd frontend && npx playwright test
```

## License

All rights reserved.
