# Roadmap

## What's done

- [x] **QStash cron activation** — 5 background jobs registered on startup via `config/jobs.yaml`
- [x] **Process-conversation delayed trigger** — QStash dispatch wired in `chat.py` after response saved
- [x] **Error tracking** — Langfuse tracing on all LLM calls, tool steps, jobs. Admin API for error inspection
- [x] **LLM streaming timeout** — 60s `asyncio.timeout()` wraps the entire pipeline
- [x] **Sprint 0** — Landing page redesign with demo chat, UI polish, PWA install prompt, accessibility pass, frontend testing setup
- [x] **Flow visualization** — Streamlit dashboard + GitHub-renderable Mermaid markdown files in `viz/`

---

## Phase 1.5 — Communicate the Vision

Goal: Someone landing on unspool.life immediately understands what this is and why it's different — before they sign up. Blocks sharing with friends/early testers.

- [x] **Landing page redesign** — New landing page with demo chat (edge function), hero section, feature showcase, pricing, testimonials-ready layout. Sprint 0 completion
- [ ] **Demo interaction polish** — The demo chat exists but needs better sample conversations, smoother animations, and mobile responsiveness tuning
- [ ] **Explainer content** — Short video/screencast (~30s) or illustrated walkthrough showing the ADHD problem → Unspool solution flow. Current landing page explains features but doesn't show the emotional arc

---

## Phase 2A — Foundation Hardening

Goal: Sleep-at-night security and reliability before anyone else touches this. Blocks real users beyond dogfooding.

**Safety:**
- [x] **Prompt injection protection** — `<user_input>` boundary markers in all 26 Jinja2 templates (direct user input + stored user-derived data) + system prompt instruction to treat tagged content as untrusted
- [x] **Pydantic validation on LLM JSON outputs** — Schema models for intent classification, item extraction, query analysis, emotional detection; validate in `engine.py` after `_extract_json()`; log warning + fallback to raw dict on validation failure
- [x] ~~**Content filtering/logging**~~ — SKIPPED: regex-based detection provides false security; `<user_input>` tags are the real defense

**Reliability:**
- [x] **Atomic rate limiting** — `SET key 0 EX 86400 NX` then `INCR` — expiry always set atomically with key creation
- [ ] **Lower free tier rate limit** — `gate.yaml` has 1000 msgs/day (kept high for pre-launch testing). Lower to 10 when Stripe subscriptions are live
- [x] **Streaming response save reliability** — `finally` block in generator ensures save even on client disconnect; mutable `stream_state` dict tracks completion/failure; `metadata.partial=true` on incomplete streams

**Security:**
- [x] **Security headers** — `frontend/vercel.json` with CSP (including img-src for Google avatars, worker-src for PWA), HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy (microphone allowed)
- [x] **Multi-stage Dockerfile** — `python:3.11-slim-bookworm`, separate builder/runtime stages, non-root `appuser`, HEALTHCHECK, `.dockerignore`
- [x] **Dependency pinning** — `pip-compile` with `requirements.in`/`requirements-dev.in`. Versions fully pinned (hashes removed for cross-platform CI compat)
- [x] **Dependency vulnerability scanning** — `pip-audit` in CI, checks pinned deps against Python Packaging Advisory Database

**Config validation:**
- [x] **Pydantic models for all config files** — `types.py` dataclasses → Pydantic `BaseModel` with `extra="forbid"`. `config_models.py` covers all 7 YAML configs. Server refuses to start on validation failure
- [x] **Cross-reference validation at startup** — Intents → pipeline files, pipeline steps → tools + prompts. Runs after tool auto-discovery in `main.py` lifespan

---

## Phase 2B — Testing & Eval Framework

Goal: Iterate on prompts and scoring without praying. Every change is regression-tested. Blocks confident iteration.

**LLM Eval tests:**
- [ ] **Golden test cases for intent classification** — 30+ real messages with expected intents, run through classify_intent with recorded/real LLM, pytest `--eval` marker for separate runs
- [ ] **Golden test cases for item extraction** — 15+ brain dumps with expected extracted items (count, interpreted_action, deadline_type, energy_estimate)
- [ ] **Eval CI integration** — Run evals on a schedule (not every PR, since they need LLM calls), report regressions

**Unit/integration tests:**
- [ ] **pick_next scoring tests** — Crafted item lists asserting correct selection (all same urgency, hard deadline today vs high-urgency soft, never-surfaced boost, etc.) — pure unit, no LLM
- [ ] **pick_next per-boost breakdown logging** — Log `urgency_base`, `deadline_boost`, `energy_boost`, `surfaced_boost` per item in `momentum_tools.py`, link to trace_id
- [x] **Frontend testing setup** — Vitest with critical path tests. Sprint 0 completion
- [x] **OpenAPI snapshot test** — `test_openapi_snapshot.py` compares `app.openapi()` against committed snapshot; `UPDATE_SNAPSHOTS=1` to regenerate; fails in CI if snapshot missing
- [x] **Config loading test** — Parametrized pytest for all pipeline YAMLs (dynamically discovered) + all config files via Pydantic models + cross-reference validation

**Dev tooling:**
- [x] **Pre-commit hooks** — `.pre-commit-config.yaml`: ruff check --fix, ruff format, check-yaml, no-commit-to-branch (main), check-added-large-files
- [x] **Pre-push hook** — Runs `pytest -x --timeout=30` on backend changes before push
- [x] **Claude Code hooks** — `PostToolUse`: ruff format on .py edits. `PreToolUse`: block migration/env writes. `Stop`: run test suite
- [x] **Pyright in CI** — `npx pyright@1.1.408` with `pyrightconfig.json` (basic mode). All type errors fixed properly
- [x] **Dependabot** — `.github/dependabot.yml` for pip, npm, and github-actions; weekly; grouped minor+patch

---

## Phase 2C — Operational Completeness

Goal: Every feature in PRODUCT_SPEC.md actually works end-to-end. v0.1 spec fulfilled.

- [ ] **Stripe checkout wiring** — `/api/subscribe` → Stripe API, webhook handler for checkout.completed/subscription.deleted/payment.failed, update user tier in DB
- [ ] **Google Calendar OAuth user flow** — User-facing consent from within chat (meta intent), sync backend already exists
- [ ] **Push notification e2e** — Verify VAPID on real devices (iOS 16.4+, Android Chrome), test check-deadlines → proactive message → device notification path
- [ ] **Concurrent message handling** — Users send while AI processes; queue in InputBar, pending visual state, message ordering guarantees, context assembly for in-flight messages
- [ ] **Frontend 429 error handling** — Chat shows generic "couldn't reach the server" on rate limit. Should parse 429 response body and show the actual message ("You've reached your daily message limit"). Also show upgrade prompt for free tier users
- [x] **UI polish pass** — Animation jank, responsive edge cases, sent-while-offline indicator. Sprint 0 completion
- [x] **PWA install prompt** — Device-aware "add to home screen" suggestion. Sprint 0 completion
- [ ] **Account deletion via chat** — Meta intent with confirmation step, uses existing `DELETE /api/account`
- [ ] **Item update/correction via chat** — "the meeting moved to Wednesday" / "actually the deadline is next Friday" — user needs to correct the AI's understanding of an existing item (deadline, description, etc.) from conversation
- [ ] **Item removal via chat** — "forget about the dentist" / "never mind about that" — user wants to delete or deprioritize a specific item. Needs matching + removal to work reliably, not just a generic meta response
- [ ] **Offline message queuing** — Frontend queues messages typed while offline and sends them when connection returns. Offline banner exists but messages typed offline are currently lost

---

## Phase 2D — Backend Hardening

Goal: Handle 50+ concurrent users without things breaking.

- [ ] **Decay job pagination** — `get_all_open_items_for_decay()` loads ALL items into memory; add cursor-based pagination
- [ ] **Batch update SQL** — `batch_update_items()` runs N individual queries; refactor to `UPDATE ... FROM (VALUES ...)`
- [x] **Async Redis client** — Migrated to native `upstash_redis.asyncio.Redis`; rate_limit_check uses pipelining (2 HTTP calls → 1)
- [ ] **Connection pool tuning** — asyncpg `max_size=10`; add `pool.acquire(timeout=5)`, consider raising pool size
- [x] **ASGI middleware for tracing** — Raw ASGI middleware replacing BaseHTTPMiddleware; fixes SSE streaming buffering; `scope["state"]["trace_id"]` + `send_wrapper` for header injection
- [x] **Prompt file caching** — `_env.get_template()` with Jinja2's built-in mtime cache; frontmatter stripped in `_PromptLoader.get_source()`; eager hash computation in `get_prompt_hash()`
- [ ] **Timezone-aware operations** — Rate limiting resets at user's local midnight, but also deadline calculations (check_deadlines job, proactive triggers, urgency decay) need user timezone for correct "24 hours away" / quiet hours logic
- [x] **Graph memory integration** — Postgres-native graph (memory_nodes + bi-temporal memory_edges + node_neighbors cache), halfvec embeddings, trigger-based retrieval, token-budgeted serialization, shadow mode. See `docs/GRAPH_MEMORY.md`
- [ ] **Graph evolution cron job** — Daily per-user evolution: embedding generation, edge decay, weak edge pruning, LLM synthesis (merges, contradictions), neighbor cache rebuild
- [ ] **Migration rollback scripts** — Write a paired `00NNN_<name>.down.sql` for every migration. Two-phase destructive DDL: before dropping a column, (1) deploy code that stops reading it, (2) confirm stable, (3) drop in the next migration

---

## Phase 3 — Interaction Quality & Personalization

Goal: The AI feels genuinely smart and personal. "It gets me."

**Conversation intelligence:**
- [ ] **Multi-step confirmations** — Destructive actions (delete account, mass deprioritize, cancel subscription) check recent_messages for confirmation before executing
- [ ] **Disambiguation responses** — fuzzy_match_item with multiple matches asks "which one?", resolves from conversation context on next message
- [ ] **Action buttons from backend** — Parse `[button text]` patterns in response, emit SSE `actions` event, strip from saved text (frontend already handles the event)
- [ ] **Focus mode** — Single-task mode, AI refuses additions and redirects to current task, session-level state in Redis
- [ ] **Task decomposition** — When a task feels too big ("write chapter 3"), AI offers to break it into 5-15 minute chunks specific to what the user has mentioned. Key ADHD feature — the blocker isn't the task, it's that the task is too large to start
- [ ] **Counter-catastrophizing with data** — "I'm not getting anywhere" → AI pulls actual completion stats and counters with real data ("you've done 47 things this month"). Emotional responses need access to item_events data to ground reassurance in facts, not platitudes
- [ ] **Duplicate / already-tracked detection** — User says "need to do laundry" when laundry is already an open item. AI should handle gracefully — acknowledge without creating a duplicate, or update the existing item with new context
- [ ] **"Chill" / adjust nudging intensity** — User says "stop nudging me" or "chill" → AI backs off proactive messages significantly. Needs a pushiness adjustment that persists across sessions, not just one-time acknowledgment

**Personalization:**
- [ ] **Apply preference inference to profile** — detect_patterns writes to `patterns` JSONB but never updates actual columns (tone/length/pushiness/emoji/language); apply high-confidence results
- [ ] **Explicit preference tool** — "be more pushy" / "use emoji" detected as intent, updates profile directly
- [ ] **Memory-to-profile enrichment** — Extract structured fields (occupation, location, timezone) from memories into profile columns
- [ ] **Pattern insight surfacing in conversation** — Patterns are detected daily and stored in `user_profiles.patterns`, but never shown to the user. AI should weave insights into responses naturally ("I noticed you're productive early in the week...") — not as reports, conversationally
- [ ] **Multi-language response** — Language is detected and stored in `primary_language` but prompts don't instruct the LLM to respond in that language. Need prompts to use the detected language and handle mid-conversation language switching

**Smart scheduling:**
- [ ] **Recurrence detection** — Detect "user creates 'do laundry' weekly" pattern, offer to make recurring
- [ ] **Snooze via QStash** — "remind me Tuesday" creates delayed QStash job targeting nudge endpoint; infrastructure ready, needs endpoint + pipeline
- [ ] **Deprioritized-to-open reactivation** — Semantic match against deprioritized items when user mentions something related, offer to reactivate

---

## Phase 4 — Growth & Product Completeness

Goal: From "works for me" to "works for paying strangers."

**Observability & analytics:**
- [ ] **Frontend analytics** — PostHog or minimal custom tracker; events: message_sent, voice_used, PWA_installed, upgrade_prompt_shown/converted (no PII)
- [ ] **Business event tracking** — Structured events table: item_created, item_completed, pick_next_served, subscription_started/cancelled; queryable via SQL
- [ ] **Langfuse usage audit** — Verify all 10 pipelines report token usage; find gaps via null usage query
- [ ] **Sentry integration** — Free tier for error tracking with push notifications on new error types. Langfuse tracks LLM traces, admin API shows errors, but neither alerts you proactively. Sentry groups, deduplicates, and sends one alert per new issue
- [ ] **Uptime monitoring** — UptimeRobot (free) pinging `/health` every 5 min with SMS alert. Two SLOs: availability (99.5%, allows ~3.6h downtime/month) and P95 chat latency (<10s). Don't over-monitor — two alerts you always act on beat twenty you ignore

**Product completeness:**
- [ ] **QUERY_OVERVIEW intent** — "what's on my plate?" narrative summary (not a list), new pipeline + prompt
- [ ] **Idea correlation** — Semantic search past items/memories when user dumps something new, surface connections above similarity threshold
- [ ] **Weekly summary push (opt-in)** — Offered after 2+ weeks active use, sent at user's typical active time
- [ ] **Free tier redesign** — Consider items-captured/day instead of messages/day (brain dump of 5 items in 1 message vs 5 "what should I do" queries — cost is asymmetric)
- [ ] **Progress summaries for multi-week projects** — "how's the thesis going?" → AI assembles status from weeks of done/in-progress conversational mentions. Different from QUERY_OVERVIEW (current snapshot) — this is about tracking a project's arc over time
- [ ] **Explain suggestion reasoning** — "why did you suggest this?" → AI explains its pick_next logic transparently: "it's due tomorrow and it's a quick one." Builds trust, especially when suggestions feel wrong
- [ ] **Data export** — "can I get my data?" → JSON/CSV export of items, messages, and profile. GDPR requirement and trust-builder for users sharing sensitive information
- [ ] **Selective topic deletion** — "delete everything about the thesis" → remove items matching a topic, not just single items or full account deletion. Needs semantic matching + batch operation
- [ ] **Contact / feedback channel** — "I need help" / "something is broken" → clear path to reach a human surfaced in the meta pipeline. Not a chatbot loop — an actual email or form

**Launch readiness:**
- [x] **Landing page enhancement** — Demo chat, hero section, feature showcase, pricing layout. Sprint 0 completion
- [ ] **Privacy policy content** — What's stored, what goes to LLM providers, right to deletion, GDPR basics (LegalPage component exists)
- [ ] **Share sheet integration** — Register as PWA share target in manifest.json, capture text/URLs from other apps
- [ ] **Config-file feature flags** — Add `config/flags.yaml`, load with existing `load_config()`. Deploy risky features behind `flag: false`, flip to `true` in a separate commit. Rollback = one more commit. No external service needed; Railway redeploy is ~1-2 min
- [x] **Accessibility pass** — Screen reader labels, keyboard navigation, `prefers-reduced-motion`, WCAG AA contrast. Sprint 0 completion
- [ ] **Share link** — Easy way to share Unspool with a friend. Just a copyable link, not an invite system

**Orchestrator DX:**
- [x] **Flow visualization tool** — `viz/` directory with Streamlit dashboard (`streamlit run viz/app.py`) and static Mermaid markdown files (`python viz/generate.py`). 7 interactive views: message flow, 10 pipeline details, background jobs, database access map, proactive messages, config dependencies, impact matrix. Dashboard has zoom/pan, inline file viewer, dark theme. Markdown files render natively on GitHub
- [ ] **Config versioning + diffing** — Track config hashes across deploys (config_loader already hashes files), surface config changes in Langfuse trace metadata so you can correlate prompt/config changes with quality shifts
- [ ] **Prompt rollback** — Revert a specific prompt template to a previous git version without reverting everything else (git-based, not a separate versioning system)

---

## Phase 5 — Platform & Scaling

Goal: Multi-platform, better voice, more integrations. Only when current infrastructure strains.

- [ ] **Capacitor native wrapper** — iOS/Android app store, native push via APNs/FCM (more reliable than web push on iOS)
- [ ] **Whisper/Deepgram voice upgrade** — Server-side transcription, better accuracy especially non-English
- [ ] **Email integration** — Forward emails to Unspool address, extract tasks automatically
- [ ] **Apple Calendar / Outlook Calendar**
- [ ] **Horizontal scaling** — Split /api/* and /jobs/* into separate Railway services
- [ ] **Deferred one-shot actions** — "remind me Tuesday" with QStash `dispatch_at()`, nudge-item endpoint
- [ ] **Calendar connect prompt for magic link users** — User who signed up without Google gets offered calendar connection later in chat, when calendar context would have been useful ("you mentioned a meeting but I can't check your calendar"). Conversational, not a settings page

---

## Never Build (violates core principles)

- Dashboard, settings page, admin UI (single-surface principle)
- Categories, tags, projects, folders (zero-decisions principle)
- Daily/weekly review rituals (no-clock-assumptions)
- Streaks, gamification, achievements (quiet-respect)
- Re-engagement notifications (quiet-respect)
- Light mode (not v0.1)
- Multi-channel (Telegram, Discord) — one-surface principle
