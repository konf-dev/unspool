# Unspool — Frontend V2 Specification

**For:** Claude Code / Cursor / AI code generation
**Stack:** React 19 + Vite 6 + TypeScript 5.7 + Tailwind CSS 4 + Zustand 5 + Framer Motion 12
**Output:** Progressive Web App (PWA) deployable to Vercel
**Design System:** Midnight Sanctuary (from Stitch design iterations)
**Design Philosophy:** First-person stream of consciousness. Calm, dark, anti-productivity. A quiet sanctuary, not a command center.

---

## Overview

Unspool V2 is a first-person reflection interface. The AI doesn't respond AS a chatbot — it reflects your thoughts in first person, like an external mind organizing itself.

**Core interaction:** User dumps raw thoughts → AI reflects them back refined, in first person, indented.

```
i need to finish the report by Friday and call Mom
about her birthday. feeling stressed about the report.

    I'm finishing the report by Friday. I'm calling Mom.
    I'm managing the stress.
```

**No chat bubbles. No "user" vs "assistant" visual split.** Just a continuous stream where raw dumps are followed by their refined reflections. Distinguished only by indentation + muted tone.

**UI:** Zero navigation. Drag handle (top), message stream (middle), input bar (bottom). Desktop: contained width (~640px max, centered) like Instagram.

---

## Screens (5 routes)

| Path | Component | Auth Required |
|------|-----------|---------------|
| `/` | `LandingPage` | No (skip if PWA standalone → `/login`) |
| `/login` | `LoginScreen` | No |
| `/chat` | `StreamPage` | Yes (redirect to `/login` if no token) |
| `/privacy` | `PrivacyPage` | No |
| `/terms` | `TermsPage` | No |

Routing: hand-rolled via `uiStore.route` + `window.history.pushState`. Page transitions via Framer Motion `AnimatePresence` with opacity fade 300ms.

### Login Screen
- Email OTP flow (no Google SSO for MVP)
- Two-stage: enter email → enter 6-digit code
- `inputMode="numeric"` for mobile numeric keypad
- Auto-submits on 6th digit
- Email persisted in `sessionStorage` across page refreshes
- `autoComplete="one-time-code"` for OS-level OTP autofill
- Supabase dashboard must use `{{ .Token }}` template (not `{{ .ConfirmationURL }}`)

### The Stream (main screen)
- Fullscreen stream interface
- Message area takes full height minus input bar
- Empty state: "just start typing — I'll remember everything"
- `UserThought` — raw user input, left-aligned, `text-on-surface/80`, no bubble
- `Reflection` — AI first-person, indented `pl-6`, muted `text-on-surface-variant`, markdown
- `StreamingText` — token-by-token with blinking cursor, buffers incomplete `[action](...)` patterns
- `ThinkingIndicator` — sage pulse dot
- `ToolStatus` — "remembering...", "updating..." labels
- `ActionChips` — sage ghost buttons below reflections, staggered 80ms entrance

### The Plate (drag overlay)
- Framer Motion drag overlay, slides down from top
- **ALWAYS snaps back on release** — no lock threshold (anti-guilt mechanic)
- Shows AI summary + items with sage/amber dot indicators
- Chat blurs/dims when plate is visible

### Landing Page
- Auto-playing demo chat (3 sequences)
- Interactive demo on focus (5-message cap then sign-in prompt)
- "Get Started" CTA → login flow

---

## Design System: Midnight Sanctuary

From `frontend/stitch_the_plate_peek/nocturne_sanctuary/DESIGN.md`.

**Colors (Tailwind tokens in `globals.css`):**
- `background` / `surface`: #0d0e0d
- `surface-container-low`: #121411 | `surface-container`: #181a17
- `surface-container-high`: #1e201c | `surface-bright`: #292d27
- `primary`: #aecdc0 (sage) | `on-primary`: #2a463c
- `primary-container`: #304c42 | `tertiary`: #ffe7ca (amber)
- `on-surface`: #e4e6de | `on-surface-variant`: #a9aca4
- `outline-variant`: #464943 | `error`: #ee7d77
- User bubble: `#1A1815` | No pure white (#FFFFFF) anywhere

**Typography:** Manrope Variable (self-hosted woff2), line-height 1.6-1.8, light weights.

**Rules:**
- No borders for structural sectioning (depth via surface color shifts)
- No bouncy animations (ease-in-out 300-500ms)
- Ghost borders: `outline-variant` at 15% opacity max
- Glassmorphism: `surface-container` + `backdrop-filter: blur(12px)` for overlays

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | React 19 + TypeScript 5.7 |
| Build | Vite 6 |
| Styling | Tailwind CSS 4 (with `@theme` design tokens) |
| Animation | Framer Motion 12 |
| State | Zustand 5 (4 stores: auth, message, plate, ui) |
| SSE | @microsoft/fetch-event-source |
| Auth | @supabase/supabase-js (email OTP) |
| Markdown | markdown-to-jsx |
| Input | react-textarea-autosize |
| Tests | Vitest + React Testing Library + Playwright |
| PWA | vite-plugin-pwa (Workbox) |
| Deploy | Vercel |

---

## State Management (Zustand)

**authStore:** `isAuthenticated`, `isLoading`, `userId`, `token`, `sendOtp()`, `verifyOtp()`, `signOut()`, `_initSession()`

**messageStore:** `messages[]`, `streamingContent`, `isStreaming`, `isThinking`, `toolStatus`, `queue[]`, `sendMessage()`, `stopStreaming()`, `fetchHistory()`, `handleAction()`, `flushQueue()`. Messages use `role: 'user' | 'reflection'` (not 'assistant').

**plateStore:** `summary`, `items[]`, `isOpen`, `setOpen()`, `updateFromMessages()`

**uiStore:** `route`, `isOnline`, `prefersReducedMotion`, `navigate()`, `setOnline()`, `_initRoute()`

---

## File Structure

```
frontend/
├── api/
│   └── demo-chat.ts                  # Vercel Edge Function — landing page demo LLM
├── src/
│   ├── main.tsx                      # Entry point
├── App.tsx                           # Route shell + auth gating + AnimatePresence
├── styles/
│   ├── globals.css                   # @font-face, @theme tokens, Tailwind base
│   └── animations.css                # Keyframes: pulse-sage, fade-in, cursor-blink
├── types/
│   ├── index.ts                      # Message, PlateItem, ParsedSSEEvent, Route
│   └── env.d.ts                      # ImportMetaEnv types
├── stores/
│   ├── authStore.ts                  # Session, token, OTP send/verify
│   ├── messageStore.ts               # Messages, streaming, offline queue
│   ├── plateStore.ts                 # Plate items, summary, open state
│   └── uiStore.ts                    # Route, isOnline, reducedMotion
├── lib/
│   ├── supabase.ts                   # Supabase client init
│   ├── api.ts                        # SSE streaming + fetchMessages
│   ├── demo-api.ts                   # Landing page demo chat
│   ├── constants.ts                  # MAX_LENGTH, TOOL_LABELS
│   └── parseActions.ts               # [label](action:value) parser
├── hooks/
│   ├── useAuth.ts                    # Thin hook over authStore
│   ├── useChat.ts                    # SSE send/receive + queue
│   ├── useVoice.ts                   # Web Speech API
│   ├── useOffline.ts                 # Thin hook over uiStore.isOnline
│   ├── usePWAInstall.ts              # Install prompt
│   ├── usePush.ts                    # Push notifications
│   ├── useScrollAnchor.ts            # Auto-scroll + scroll-lock
│   └── useReducedMotion.ts           # prefers-reduced-motion
└── components/
    ├── shared/                       # DragHandle, AmbientGlow, PulseDot, Button
    ├── landing/                      # LandingPage, DemoChat, DemoMessage
    ├── auth/                         # LoginScreen (email OTP two-stage)
    ├── stream/                       # StreamPage, MessageList, UserThought,
    │                                 # Reflection, StreamingText, ThinkingIndicator,
    │                                 # ToolStatus, ActionChips, InputBar, VoiceButton
    ├── plate/                        # PlateOverlay, PlateSummary, PlateItem, PlateHandle
    ├── legal/                        # PrivacyPage, TermsPage
    └── system/                       # OfflineBanner, PWAInstallPrompt, ErrorBoundary,
                                      # LoadingScreen
```

---

## Backend API Endpoints

| Endpoint | Method | Auth | Frontend Use |
|----------|--------|------|-------------|
| `/api/chat` | POST (SSE) | JWT | Chat streaming |
| `/api/messages` | GET | JWT | Message history (cursor pagination) |
| `/api/subscribe` | POST | JWT | Stripe checkout |
| `/api/push/subscribe` | POST | JWT | Push notification registration |
| `/api/account` | DELETE | JWT | GDPR account deletion |
| `/health` | GET | None | Health check |

**SSE Event Types:**
- `{"type": "token", "content": "..."}` — token-by-token streaming
- `{"type": "tool_start", "calls": ["tool_name"]}` — tool execution started
- `{"type": "tool_end", "name": "tool_name"}` — tool execution finished
- `{"type": "done"}` — stream complete

---

## Key Patterns

**Streaming:** RAF-batched token accumulation. Incomplete `[action](...)` patterns buffered to prevent flicker. Abort via `AbortController`. Concurrent send prevention via `isStreaming` guard.

**Offline Queue:** Messages queued in localStorage when offline. Flushed one-by-one on reconnect. Queued messages show "queued" indicator.

**Draft Persistence:** 500ms debounced save to localStorage. Cleared after send.

**Voice Input:** Web Speech API with 3s silence auto-stop. Transcript appears in input for review (not auto-sent). Haptic feedback on start/stop.

**Push Notifications:** Auto-requested after 6+ messages in standalone PWA mode. Non-critical (silently fails).

---

## Tests

**Unit (Vitest):** 17 tests — stores, API parsing, action parsing.
**E2E (Playwright):** Auth flows, landing page, accessibility (5 spec files).

```bash
npm run test        # Vitest unit tests
npm run typecheck   # tsc --noEmit
npm run build       # Production build
npm run e2e         # Playwright E2E
```

---

## Vercel Serverless Functions

The frontend includes a Vercel Edge Function for the landing page demo chat:

- `api/demo-chat.ts` — Lightweight LLM-powered demo (Gemini Flash via OpenAI-compatible API)
- No auth required, 5-message cap per session, 150 max tokens
- System prompt coaches subtle sign-in nudge after 2-3 exchanges
- Uses `GOOGLE_API_KEY` (same key as the backend)

**Note:** This function only runs on Vercel (or `vercel dev`). With `vite dev`, the interactive demo falls back gracefully — the auto-play sequences still work.

---

## Environment Variables

Set on Vercel dashboard for Production + Preview. Never commit to code.

| Variable | Purpose | Environments |
|----------|---------|-------------|
| `VITE_API_URL` | Backend API URL (`https://api.unspool.life`) | Production, Preview |
| `VITE_SUPABASE_URL` | Supabase project URL | Production, Preview |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key | Production, Preview |
| `VITE_VAPID_PUBLIC_KEY` | Web Push VAPID public key | Production, Preview |
| `GOOGLE_API_KEY` | Gemini API key (for demo-chat edge function) | Production, Preview, Development |
| `FRONTEND_URL` | Allowed CORS origin for demo-chat | Production, Preview, Development |

**Deployment:** Vercel project `frontend` at `www.unspool.life`. Auto-deploys on push to `main`. Preview deploys on PRs.
