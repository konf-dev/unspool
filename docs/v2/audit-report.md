# Code Audit Report

65 Python files, 6 YAML configs, 9 prompt templates, 6 SQL migrations. Three audit rounds completed. All findings resolved.

## All Fixed Issues

### Round 1 — Initial implementation review

1. **`__import__("datetime").timedelta`** — `queries.py` — replaced with proper import.
2. **SQLAlchemy `~startswith()` negation** — `synthesis.py` — replaced with `not_(..like())`.
3. **Unused variable `user_event_id`** — `chat.py` — removed.

### Round 2 — Security & correctness audit

4. **Email webhook had zero authentication** (Critical) — Added HMAC-SHA256 verification via `EMAIL_WEBHOOK_SECRET`.
5. **Semantic dedup had no similarity threshold** (Critical) — `search_nodes_semantic()` now accepts `max_distance`. Cold path uses `0.1` (cosine similarity >= 0.9), enforced in SQL WHERE clause.
6. **LLM usage never recorded** (Medium) — `save_llm_usage()` wired into hot path, cold path, proactive engine, pattern detection.
7. **New AsyncOpenAI client per call** — Created `src/integrations/openai.py` singleton. All 5 call sites updated.
8. **Module-level LLM instantiation** — `hot_path/graph.py` now uses lazy `_get_llm_with_tools()`.
9. **Synthesis webhook body double-read** — Moved to `POST /jobs/synthesis` on QStash-authed router.
10. **Inline datetime import hack** — `chat.py` — cleaned up.
11. **Missing `__init__.py`** — Added `src/api/__init__.py`.

### Round 3 — Runtime testing fixes

12. **SQLAlchemy 2.0.30 incompatible with Python 3.14** — Upgraded to `>=2.0.40`.
13. **LangChain 0.0.66 incompatible with Python 3.14** — Upgraded to `langgraph>=0.4`, `langchain-openai>=0.3`.
14. **`::uuid` cast conflicts with SQLAlchemy text() params** — asyncpg uses `$1` positional params, and `::uuid` after a `:param` creates `$1::uuid` which becomes a stray colon. Removed all `::uuid` casts (Postgres auto-casts UUID strings). Used `CAST(:param AS uuid)` where explicit cast needed.
15. **`$N IS NULL` ambiguous in asyncpg** — `get_messages_from_events` used `(:before_id IS NULL OR ...)` pattern which asyncpg can't infer the type for when the parameter is NULL. Split into two separate queries (with/without cursor).
16. **QStash token missing base64 padding** — Token in `.env` was missing trailing `=`. Fixed in env. Added `QSTASH_URL` support for EU region endpoint.
17. **GDPR deletion missed operational tables** — `delete_user_data()` now also deletes from `error_log` and `llm_usage` (which store user_id as TEXT, not FK). All 10 tables covered.
18. **requirements.txt pinned to exact versions** — Changed all `==` pins to `>=` minimum versions for forward compatibility.
19. **`.env` not found when running from `backend/`** — `.env` lives at repo root. Documented symlink step: `ln -sf ../.env .env`.
20. **Stale V1 QStash schedule** — Deleted `unspool-sync-calendar` (Google Calendar sync removed in V2).

## Security Assessment

| Area | Status | Notes |
|------|--------|-------|
| Auth on user endpoints | Pass | `Depends(get_current_user)` — JWT or eval token |
| Auth on admin endpoints | Pass | Router-level `Depends(verify_admin_key)` — HMAC |
| Auth on job endpoints | Pass | Router-level `Depends(verify_qstash_signature)` |
| Auth on email webhook | Pass | HMAC-SHA256 via `EMAIL_WEBHOOK_SECRET` |
| Auth on Stripe webhook | Pass | `Stripe-Signature` header verification |
| CORS | Pass | Restricted to `FRONTEND_URL` + `CORS_EXTRA_ORIGINS` |
| Input validation | Pass | Pydantic models with length limits |
| SQL injection | Pass | All queries parameterized (named params + `CAST()`) |
| Template injection | Pass | Jinja2 SandboxedEnvironment + user input escaping |
| user_id isolation | Pass | Injected from JWT, never from request body |
| RLS | Pass | All user tables have Postgres-level RLS policies |
| PII in logs | Pass | `scrub_pii()` for Langfuse |
| GDPR deletion | Pass | All 10 tables wiped including operational |
| OpenAI client | Pass | Singleton, API key resolved once |
| LLM telemetry | Pass | All LLM calls recorded to `llm_usage` |
| Docs in production | Pass | Disabled when `ENVIRONMENT != development` |

## Endpoint Verification Matrix

All 22 endpoints verified locally on 2026-03-23. See [Testing Guide](testing.md) for reproduction steps.

| # | Endpoint | Auth | Verified |
|---|----------|------|----------|
| 1 | `GET /health` | None | Pass |
| 2 | `POST /api/chat` | JWT/eval | Pass — full pipeline |
| 3 | `GET /api/messages` | JWT/eval | Pass — with pagination |
| 4 | `POST /api/subscribe` | JWT/eval | Pass — correct error without Stripe key |
| 5 | `POST /api/push/subscribe` | JWT/eval | Pass — saves to DB |
| 6 | `POST /api/webhooks/stripe` | Stripe-Sig | Pass — rejects without signature |
| 7 | `DELETE /api/account` | JWT/eval | Pass — GDPR cascade, 10 tables |
| 8 | `GET /api/feed/{token}.ics` | Token-URL | Pass — 404 for bad token |
| 9 | `POST /webhooks/email/inbound` | HMAC | Pass — 403 without secret/signature |
| 10 | `POST /jobs/synthesis` | QStash | Pass — 403 without signature |
| 11 | `POST /jobs/hourly-maintenance` | QStash | Pass — 403 without signature |
| 12 | `POST /jobs/nightly-batch` | QStash | Pass — 403 without signature |
| 13 | `POST /jobs/process-message` | QStash | Pass — 403 without signature |
| 14 | `POST /jobs/execute-action` | QStash | Pass — 403 without signature |
| 15 | `GET /admin/trace/{id}` | Admin key | Pass |
| 16 | `GET /admin/user/{id}/messages` | Admin key | Pass |
| 17 | `GET /admin/user/{id}/graph` | Admin key | Pass |
| 18 | `GET /admin/user/{id}/profile` | Admin key | Pass |
| 19 | `GET /admin/jobs/recent` | Admin key | Pass — LLM usage present |
| 20 | `GET /admin/errors` | Admin key | Pass — with stacktraces |
| 21 | `GET /admin/errors/summary` | Admin key | Pass |
| 22 | `DELETE /admin/eval-cleanup` | Admin key | Pass |
| 23 | `GET /admin/health/deep` | Admin key | Pass — all 4 services ok |

## Test Coverage

8 test modules (conftest + 7 test files). Unit tests with mocking. Integration tests against a real database are not yet implemented but the smoke test script in [Testing Guide](testing.md) covers end-to-end verification.
