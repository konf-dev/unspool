# Deployment Guide

## Architecture Overview

```
Browser (PWA)  →  Vercel (static)
     │
     ▼ HTTPS
FastAPI server  →  Railway
     │
     ├── Supabase (Postgres + pgvector + Auth)
     ├── Upstash Redis (cache + rate limits)
     ├── Upstash QStash (cron jobs)
     ├── Anthropic/OpenAI (LLM + embeddings)
     ├── Google Calendar API
     └── Stripe
```

---

## 1. Supabase Setup

### Create project
1. Go to [supabase.com](https://supabase.com), create a new project
2. Note your project URL and keys from Settings → API

### Run migrations
```bash
cd backend

# Option A: Supabase CLI (recommended)
npx supabase db push

# Option B: Manual — copy-paste each migration file into the SQL Editor
# Run 00001_initial_schema.sql first, then 00002_vector_indexes_and_hybrid_search.sql
```

### Configure Auth
1. Settings → Authentication → Providers → Enable Google
2. Add your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
3. Set redirect URL to your frontend domain
4. Settings → Authentication → URL Configuration → Set Site URL to your frontend domain

### Get keys
From Settings → API:
- **Project URL** → `SUPABASE_URL`
- **Publishable key** (anon public) → `SUPABASE_PUBLISHABLE_KEY`
- **Secret key** (service_role secret) → `SUPABASE_SECRET_KEY`

From Settings → API → JWT Settings:
- **JWT Secret** (current active key) → `SUPABASE_JWT_SIGNING_SECRET`

From Settings → Database → Connection string (URI):
- → `DATABASE_URL` (use the one with your password)

---

## 2. Upstash Setup

### Redis
1. Create a Redis database at [upstash.com](https://upstash.com)
2. Copy REST URL and token → `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`

### QStash
1. Enable QStash in the same Upstash account
2. Copy token → `QSTASH_TOKEN`
3. Copy signing keys → `QSTASH_CURRENT_SIGNING_KEY`, `QSTASH_NEXT_SIGNING_KEY`

### Set up cron schedules
After deploying the backend, create QStash schedules:

| Job | URL | Cron |
|-----|-----|------|
| Check deadlines | `POST https://your-api.railway.app/jobs/check-deadlines` | `0 * * * *` (hourly) |
| Decay urgency | `POST https://your-api.railway.app/jobs/decay-urgency` | `0 */6 * * *` (every 6h) |
| Sync calendar | `POST https://your-api.railway.app/jobs/sync-calendar` | `0 */4 * * *` (every 4h) |
| Detect patterns | `POST https://your-api.railway.app/jobs/detect-patterns` | `0 3 * * *` (daily 3am) |

`process-conversation` is triggered per-request, not on a cron.

---

## 3. LLM Setup

### Anthropic (recommended for chat)
1. Get API key from [console.anthropic.com](https://console.anthropic.com)
2. Set `LLM_API_KEY`, `LLM_PROVIDER=anthropic`
3. Models: `LLM_MODEL=claude-sonnet-4-20250514`, `LLM_MODEL_FAST=claude-haiku-4-5-20251001`

### OpenAI (required for embeddings)
1. Get API key from [platform.openai.com](https://platform.openai.com)
2. Set `EMBEDDING_API_KEY`, `EMBEDDING_PROVIDER=openai`, `EMBEDDING_MODEL=text-embedding-3-small`

---

## 4. Deploy Backend (Railway)

### From the Railway dashboard
1. Create new project, connect your GitHub repo
2. Set root directory to `backend`
3. Railway will detect the Dockerfile automatically

### Environment variables
Set all env vars from `.env.example` in the Railway dashboard. Key ones:

```
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SECRET_KEY
SUPABASE_JWT_SIGNING_SECRET
DATABASE_URL
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
QSTASH_TOKEN
QSTASH_CURRENT_SIGNING_KEY
QSTASH_NEXT_SIGNING_KEY
LLM_API_KEY
LLM_MODEL
LLM_MODEL_FAST
LLM_PROVIDER
EMBEDDING_API_KEY
EMBEDDING_MODEL
EMBEDDING_PROVIDER
ENVIRONMENT=production
FRONTEND_URL=https://unspool.life
VAPID_PRIVATE_KEY
VAPID_PUBLIC_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
```

### Verify
```bash
curl https://your-api.railway.app/health
# → {"status": "ok"}
```

---

## 5. Deploy Frontend (Vercel)

### From the Vercel dashboard
1. Import the repo, set root directory to `frontend`
2. Framework preset: Vite
3. Build command: `npm run build`
4. Output directory: `dist`

### Environment variables
```
VITE_API_URL=https://your-api.railway.app
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your-publishable-key
VITE_VAPID_PUBLIC_KEY=your-vapid-public-key
```

### Custom domain
1. Add `unspool.life` as a custom domain in Vercel
2. Update DNS records as instructed
3. Update `FRONTEND_URL` in Railway env vars to match

---

## 6. Stripe Setup (post-MVP)

1. Create Stripe account, get secret key → `STRIPE_SECRET_KEY`
2. Set up webhook endpoint: `https://your-api.railway.app/api/subscribe/webhook`
3. Subscribe to events: `checkout.session.completed`, `customer.subscription.deleted`, `invoice.payment_failed`
4. Copy webhook signing secret → `STRIPE_WEBHOOK_SECRET`

---

## 7. VAPID Keys (Push Notifications)

Generate a VAPID key pair:

```bash
npx web-push generate-vapid-keys
```

Set `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY` in both Railway and Vercel env vars.

---

## Local Development

```bash
# Backend
cd backend
cp ../.env.example .env   # Edit with your actual values
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173

# Tests
cd backend
pytest -v
```

Set `VITE_USE_MOCKS=true` in `frontend/.env.development` to run the frontend without a backend.

---

## Monitoring

- **LLM usage:** Query the `llm_usage` table for token spend per pipeline/model
- **Health:** `GET /health` returns `{"status": "ok"}`
- **Logs:** Structured JSON via structlog — Railway captures stdout automatically
- **Errors:** Each request gets a `trace_id` in the `X-Trace-Id` response header
