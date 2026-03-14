# Roadmap

## Phase 2 — Get to chat-workflow-only mode

Goal: Make the app solid enough that all future work is config/prompts/tools changes.

### Must-do (blocks chat workflow iteration)

- [ ] **UI polish** — Fix jankiness, animations, transitions, responsiveness, edge cases
- [ ] **Concurrent message handling** — Let users send messages while AI is processing. Touches UI (InputBar, useChat), message ordering, and backend context assembly
- [ ] **QStash cron activation** — Schedule the 5 background jobs (check-deadlines hourly, decay-urgency 6h, process-conversation after chat, sync-calendar 4h, detect-patterns daily)
- [ ] **Process-conversation delayed trigger** — Wire QStash to fire embeddings/dedup/profile extraction after each chat
- [ ] **Push notification e2e** — Verify VAPID keys, test on real device, confirm proactive message delivery

### Should-do (important but doesn't block chat iteration)

- [ ] **Orchestrator DX** — Config versioning, flow visualization, diffing, rollback. Makes iterating on pipelines/prompts fast
- [ ] **Account deletion via chat** — Meta intent sub-flow with confirmation step
- [ ] **PWA install prompt** — Device-aware "add to home screen" suggestion in chat (iOS Safari, Android Chrome, desktop)
- [ ] **Stripe checkout wiring** — Connect /api/subscribe to Stripe API, webhook setup
- [ ] **Google Calendar OAuth user flow** — User-facing calendar connection (sync backend already exists)

### Hardening

- [ ] **CSP headers**
- [ ] **Error tracking** — Sentry or similar
- [ ] **Service worker cache strategy**

## Out of scope (v0.2+)

- Capacitor native wrapper (iOS/Android)
- Native push via APNs/FCM
- Email integration
- Apple Calendar / Outlook Calendar
- Deepgram/Whisper voice upgrade
- QUERY_OVERVIEW intent (narrative summary of what's on your plate)
