# Deployment Log — Unspool v0.1

First production deployment completed 2026-03-13.

---

## Production URLs

| Service | URL |
|---------|-----|
| Frontend | https://www.unspool.life |
| Frontend (root) | https://unspool.life |
| API | https://api.unspool.life |
| API health check | https://api.unspool.life/health |
| Railway internal | backend-production-36f2.up.railway.app |
| Vercel internal | frontend-two-opal-93.vercel.app |

---

## Service Accounts

| Service | Plan | Dashboard |
|---------|------|-----------|
| Railway | Developer ($5/mo) | railway.app |
| Vercel | Pro (trial) | vercel.com |
| Supabase | Free tier | supabase.com |
| Upstash Redis | Free tier | upstash.com |
| Upstash QStash | Free tier | upstash.com |
| Cloudflare | Free tier | cloudflare.com (DNS + SSL) |
| GoDaddy | Domain registrar | godaddy.com (nameservers point to Cloudflare) |
| Google Cloud | OAuth consent screen | console.cloud.google.com |

---

## DNS Setup (Cloudflare)

GoDaddy nameservers changed to Cloudflare. All DNS managed in Cloudflare.

| Type | Name | Value | Proxy |
|------|------|-------|-------|
| A | @ | 216.198.79.1 | Off |
| CNAME | www | 1a184c40ef356e70.vercel-dns-017.com | Off |
| CNAME | api | wf1mvmav.up.railway.app | Off (required) |
| TXT | _railway-verify.api | railway verification string | Off |

**Important:** All records are DNS only (no Cloudflare proxy). Railway and Vercel handle their own SSL. Proxying can cause SSL conflicts.

SSL/TLS mode: **Full (strict)**.

---

## Auth Flow

```
User → Google OAuth → Supabase Auth → ES256 JWT → Backend verifies via JWKS
```

- Supabase new projects use **ES256** (asymmetric) JWT signing, not HS256
- Backend fetches public keys from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
- PyJWT library with `cache_jwk_set=True, lifespan=600` for key caching
- Algorithm is hardcoded to `["ES256"]` to prevent algorithm confusion attacks
- JWT is validated for: signature, expiry, audience (`authenticated`), issuer (`{SUPABASE_URL}/auth/v1`), required claims (`exp`, `sub`, `aud`, `iss`)

### Supabase Auth Settings

- Site URL: `https://unspool.life`
- Redirect URLs: `https://unspool.life`, `https://unspool.life/**`, `https://www.unspool.life`, `https://www.unspool.life/**`
- Providers: Google (with calendar.readonly scope)

### Google Cloud Console

- OAuth consent screen configured
- Authorized JavaScript origins: `https://unspool.life`
- Authorized redirect URIs: `https://<project>.supabase.co/auth/v1/callback`

---

## Environment Variables

### Railway (backend)

```
ENVIRONMENT=production
FRONTEND_URL=https://unspool.life
CORS_EXTRA_ORIGINS=https://www.unspool.life,https://frontend-two-opal-93.vercel.app
DATABASE_URL=<supabase connection pooler URI, port 6543>
SUPABASE_URL=<project URL>
SUPABASE_PUBLISHABLE_KEY=<publishable key>
SUPABASE_SECRET_KEY=<service role secret>
SUPABASE_JWT_SIGNING_SECRET=<not used for ES256, kept for reference>
UPSTASH_REDIS_REST_URL=<redis URL>
UPSTASH_REDIS_REST_TOKEN=<redis token>
QSTASH_TOKEN=<qstash token>
QSTASH_CURRENT_SIGNING_KEY=<signing key>
QSTASH_NEXT_SIGNING_KEY=<next signing key>
LLM_API_KEY=<openai key>
LLM_MODEL=gpt-4.1
LLM_MODEL_FAST=gpt-4.1-nano
LLM_PROVIDER=openai
GOOGLE_CLIENT_ID=<google oauth client id>
GOOGLE_CLIENT_SECRET=<google oauth client secret>
VAPID_PRIVATE_KEY=<vapid private key>
VAPID_PUBLIC_KEY=<vapid public key>
```

### Vercel (frontend)

```
VITE_API_URL=https://api.unspool.life
VITE_SUPABASE_URL=<project URL>
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable key>
VITE_VAPID_PUBLIC_KEY=<vapid public key>
```

**Note:** `VITE_*` variables are baked into the JS bundle at build time. Changing them requires a redeploy (`vercel --prod`), not just updating the dashboard value.

---

## Deployment Steps Followed

### 1. Backend (Railway)

1. Created project in Railway, connected GitHub repo (konf-dev/unspool)
2. Set root directory to `backend` in Railway settings
3. Set Config File Path to `backend/railway.json`
4. Railway detected Dockerfile automatically (builder: DOCKERFILE)
5. Set all env vars in Railway dashboard
6. Healthcheck path: `/health`
7. Verified: `curl https://backend-production-36f2.up.railway.app/health` → `{"status":"ok"}`
8. Added custom domain `api.unspool.life` in Railway networking settings
9. Added Railway's CNAME and TXT verification records in Cloudflare

### 2. Frontend (Vercel)

1. Imported repo in Vercel, root directory: `frontend`
2. Framework preset auto-detected as Vite
3. Added env vars via `vercel env add` CLI
4. Deployed via `vercel --prod`
5. Added custom domains `unspool.life` and `www.unspool.life` in Vercel
6. Updated Cloudflare DNS records to match Vercel's recommended values

### 3. Database (Supabase)

1. Created Supabase project
2. Ran migrations manually via Supabase SQL Editor:
   - `00001_initial_schema.sql`
   - `00002_vector_indexes_and_hybrid_search.sql`
3. Used **connection pooler** URI (port 6543, Transaction mode) for `DATABASE_URL`
4. Direct connection (port 5432) requires IPv6 — pooler is more reliable

### 4. DNS (Cloudflare + GoDaddy)

1. Created Cloudflare account, added unspool.life
2. Changed GoDaddy nameservers to Cloudflare's assigned nameservers
3. Waited for nameserver propagation (~1 hour)
4. Added DNS records in Cloudflare (A, CNAME for www, CNAME for api, TXT for Railway verification)
5. Set SSL/TLS mode to Full (strict)
6. Enabled SSL/TLS Recommender

### 5. Branch Protection (GitHub)

Set via `gh api`:
- Required status checks: `test-backend`, `check-frontend`
- Require branches to be up to date
- Force pushes blocked
- Not enforced on admins (emergency escape hatch)

---

## Issues Encountered and Fixes

### Railway can't detect the app

**Symptom:** Railway build fails, says "unable to determine how to build."
**Cause:** Root directory not set to `backend`.
**Fix:** Railway Settings → set Root Directory to `backend`, Config File Path to `backend/railway.json`.

### Railway $PORT not expanding

**Symptom:** App starts but healthcheck fails. Logs show it's not listening on the right port.
**Cause:** `startCommand` in railway.json used `$PORT` but Docker builder doesn't shell-expand variables.
**Fix:** Removed `startCommand` from railway.json. The Dockerfile's `CMD` uses hardcoded port 8000, and Railway maps it automatically.

### Frontend CI build fails — "Cannot find module"

**Symptom:** `npm run build` fails in CI with TypeScript errors about missing modules in `./lib/`.
**Cause:** Root `.gitignore` had `lib/` which matched `frontend/src/lib/`, preventing those files from being committed to git.
**Fix:** Changed `.gitignore` from `lib/` to `/lib/` (anchored to repo root). Then force-added the files: `git add -f frontend/src/lib/`.

### Blank page after Google OAuth

**Symptom:** After Google sign-in, user lands on a blank page instead of chat.
**Cause:** Auth redirect in App.tsx only triggered from `/login` route, but OAuth callback returns to `/` (landing page).
**Fix:** Updated App.tsx to redirect from any non-legal route when authenticated.

### Double refresh on chat load

**Symptom:** Chat screen refreshes twice after login.
**Cause:** Auth useEffect had `route` as dependency, re-triggering when setting route to `chat`.
**Fix:** Added `route !== 'chat'` guard to prevent re-trigger.

### CORS blocking API calls

**Symptom:** Browser console shows CORS errors on API requests.
**Cause:** `FRONTEND_URL` in Railway didn't match the actual frontend domain.
**Fix:** Added `CORS_EXTRA_ORIGINS` env var support in backend. Set it to include all frontend domains (Vercel URL, unspool.life, www.unspool.life).

### All API calls returning 401

**Symptom:** Every authenticated request returns 401 "Invalid token".
**Cause:** New Supabase projects sign JWTs with **ES256** (asymmetric), not HS256. Backend was trying to verify with the JWT signing secret using HS256.
**Fix:** Rewrote `supabase_auth.py` to use PyJWT with JWKS endpoint for ES256 verification. Replaced `python-jose` with `pyjwt[cryptography]`. Backend now fetches the public key from Supabase's JWKS endpoint.

### SSE streaming not showing in chat

**Symptom:** Typing indicator shows but no text appears.
**Cause:** Backend sends `data: {"type": "token", "content": "..."}` (JSON in data field), but frontend expected SSE named events (`event: token\ndata: ...`).
**Fix:** Updated frontend `api.ts` to parse JSON from the `data` field instead of reading `event.event`.

### Chat returns 429 (rate limited) after few messages

**Symptom:** Chat stops working after 3-4 messages, returns 429.
**Cause:** `rate_limit_check` calls Redis INCR before checking the limit, so retries (from SSE library auto-retry on errors) burn through the count. Free tier was set to 10/day.
**Fix:** Raised free tier to 1000 messages/day in `config/gate.yaml`. Cleared rate limit keys in Redis via Upstash REST API: `DELETE /del/rate:{user_id}:{date}`.

### /api/auth/store-token returns 422 on every page load

**Symptom:** Noisy 422 errors in Railway logs.
**Cause:** Frontend sends `{provider_refresh_token}` but backend expected `{refresh_token, scopes}`.
**Fix:** Aligned backend `StoreTokenRequest` model to accept `provider_refresh_token` with `scopes` defaulting to `[]`.

### RLS bypass with asyncpg

**Symptom:** Not a runtime error — discovered during security audit.
**Cause:** Backend uses asyncpg (direct Postgres connection) which bypasses Supabase RLS policies. Without explicit `WHERE user_id = $x` clauses, one user could access another's data.
**Fix:** Added `user_id` to WHERE clauses in `update_item`, `batch_update_items`, `update_item_embedding` in `supabase.py`. Updated all callers to pass `user_id`.

---

## Useful Commands

```bash
# Check Railway logs
cd backend && railway logs --lines 50

# Check Railway env vars
cd backend && railway variables

# Redeploy frontend
cd frontend && vercel --prod --yes

# Check Vercel env vars
cd frontend && vercel env ls

# Reset a user's rate limit (via Upstash REST API)
# Key format: rate:{user_id}:{YYYY-MM-DD}
# DELETE https://{UPSTASH_URL}/del/{key} with Authorization: Bearer {token}

# Run backend tests locally
cd backend && pytest -x --timeout=30

# Build frontend locally (catches CI errors)
cd frontend && npm run build

# Check DNS propagation
getent hosts unspool.life
getent hosts api.unspool.life
```

---

## What's Not Set Up Yet

- [ ] QStash cron schedules (Step 7 — background jobs)
- [ ] Stripe integration (post-MVP)
- [ ] Email on @unspool.life domain (Cloudflare Email Routing + Resend)
- [ ] CSP headers
- [ ] Production rate limiting review (currently 1000/day free tier)
- [ ] Service worker cache cleanup strategy
- [ ] Root domain `unspool.life` (without www) — DNS still propagating from GoDaddy
