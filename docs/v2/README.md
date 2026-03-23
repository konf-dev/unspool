# Unspool V2 Backend Documentation

Unspool is an AI personal assistant designed for people with ADHD. The V2 backend is a complete rewrite using an event-sourced knowledge graph architecture.

## Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System architecture, event sourcing, dual-path agent design |
| [API Reference](api-reference.md) | All 22 HTTP endpoints with request/response shapes |
| [Database Design](database-design.md) | Schema, migrations, views, RLS policies |
| [Agent Design](agent-design.md) | Hot path, cold path, tools, context assembly |
| [Configuration](configuration.md) | YAML configs, environment variables, prompt templates |
| [Background Jobs](background-jobs.md) | QStash cron jobs, scheduled actions, proactive messaging |
| [Authentication & Security](auth-security.md) | JWT, QStash, admin auth, CORS, GDPR, PII scrubbing |
| [Telemetry](telemetry.md) | Structured logging, Langfuse, error reporting |
| [Testing Guide](testing.md) | Local setup, smoke tests, endpoint verification, reproducing results |
| [Deployment Guide](deployment.md) | Railway, Supabase migrations, QStash, env vars |
| [Audit Report](audit-report.md) | Code audit findings across 3 rounds, all resolved |

## Quick Start

```bash
cd backend/
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -sf ../.env .env              # .env lives at repo root
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
```

## Tech Stack

- **Runtime:** Python 3.12+ (tested on 3.14), FastAPI, Uvicorn
- **Database:** PostgreSQL + Supabase (pgvector, RLS)
- **ORM:** SQLAlchemy 2.0 async (>=2.0.40)
- **LLM:** OpenAI (model configurable via `LLM_MODEL` / `LLM_MODEL_FAST` env vars)
- **Embeddings:** text-embedding-3-small (1536 dimensions)
- **Agent Framework:** LangGraph >=0.4
- **Background Jobs:** QStash (Upstash) — EU region supported via `QSTASH_URL`
- **Cache/Rate Limiting:** Upstash Redis
- **Billing:** Stripe
- **Push Notifications:** Web Push (pywebpush + VAPID)
- **Observability:** structlog + Langfuse
- **Deployment:** Railway (Nixpacks)
