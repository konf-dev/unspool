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
| Frontend | React + Vite + TypeScript (PWA) → Vercel |
| Backend | Python 3.11+ / FastAPI / async → Railway |
| Database | Supabase (Postgres + pgvector + Auth) |
| Cache | Upstash Redis |
| Jobs | Upstash QStash (cron + delayed queue) |
| LLM | Anthropic (chat) + OpenAI (embeddings) |

## Repo Structure

```
unspool/
├── frontend/          # React PWA — single chat interface
│   ├── src/
│   │   ├── components/   # Chat UI components
│   │   ├── hooks/        # Auth, voice, push, offline
│   │   ├── lib/          # API client, Supabase, constants
│   │   └── styles/       # CSS
│   └── package.json
├── backend/
│   ├── config/           # YAML pipelines, prompts, scoring rules
│   ├── prompts/          # Jinja2 prompt templates
│   ├── src/              # FastAPI app
│   │   ├── api/          # User-facing endpoints
│   │   ├── jobs/         # Background job endpoints
│   │   ├── orchestrator/ # Config-driven message processing engine
│   │   ├── tools/        # Tool registry + implementations
│   │   ├── llm/          # LLM provider abstraction
│   │   └── db/           # Supabase + Redis clients
│   ├── tests/
│   └── requirements.txt
├── docs/                 # Detailed specs and guides
└── CLAUDE.md             # Full project context (architecture, conventions, data model)
```

See [CLAUDE.md](CLAUDE.md) for the complete architecture, data model, coding conventions, and design principles.

## Documentation

- [CLAUDE.md](CLAUDE.md) — Full project context and conventions
- [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) — Product specification
- [docs/ORCHESTRATOR_FLOW.md](docs/ORCHESTRATOR_FLOW.md) — Message processing pipeline
- [docs/FRONTEND_SPEC.md](docs/FRONTEND_SPEC.md) — UI/UX specification
- [docs/SCHEMA.md](docs/SCHEMA.md) — Database schema reference
- [docs/PIPELINE_FORMAT.md](docs/PIPELINE_FORMAT.md) — Pipeline YAML format
- [docs/TOOLS.md](docs/TOOLS.md) — Tool registry reference
- [docs/DEPLOY.md](docs/DEPLOY.md) — Deployment and infrastructure guide

## Tests

```bash
# Backend (103 tests)
cd backend && pytest -v

# Frontend (type check + build)
cd frontend && npx tsc --noEmit && npm run build
```

## License

All rights reserved.
