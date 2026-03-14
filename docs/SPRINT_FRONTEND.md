# Sprint: Frontend — Landing Page + UI Polish

**Branch:** `sprint-0/frontend`
**Scope:** Landing page redesign, UI polish, offline resilience, testing, accessibility.
**Goal:** Someone visiting unspool.life immediately understands the product, and the chat experience is polished for real users.

This is a long-running session — iterate on the landing page and UI until it feels right. Don't rush it.

---

## How to use this doc

You are a Claude session working on the `sprint-0/frontend` branch. All work is in `frontend/`. Read CLAUDE.md and `docs/FRONTEND_SPEC.md` for design conventions. Read `docs/PRODUCT_LIFECYCLE.md` Stage 1 (Discovery) and Stage 2 (First 5 Minutes) for the product perspective.

**Do not touch:** `backend/`, `.github/`, `.pre-commit-config.yaml` (another session owns those).

---

## Current State

The frontend is feature-complete for core chat. What exists:
- Full SSE streaming with token-by-token rendering
- Voice input via Web Speech API
- Google OAuth + magic link auth
- Offline detection + banner
- Message queuing in memory (volatile — lost on page reload)
- Action buttons component (ready, waiting for backend SSE events)
- PWA manifest, service worker, workbox caching
- Dark theme with CSS variables, glass morphism, Satoshi font
- Landing page with hero section, 3 feature descriptions, CTA, pricing line
- Cat easter egg in hill SVG

What's missing:
- Landing page doesn't communicate the product well enough (see Phase 1.5)
- No test framework
- Queue doesn't persist across page reloads
- No PWA install prompt in chat
- Animation and responsive edge cases
- Accessibility gaps

---

## 1. Landing Page Redesign (Phase 1.5)

This is the most important item. Someone landing on unspool.life must understand in 5 seconds: "This is NOT a todo list. You just talk to it."

### 1.1 Rethink the landing page

**Current state:** `frontend/src/components/LandingPage.tsx` — hero section with "unspool" title, one-line pitch, 3 feature descriptions, CTA button, pricing line, SVG hills background with animated stars.

**Problem from `docs/PRODUCT_LIFECYCLE.md` Stage 1:**
> The "why this is different" must land emotionally: "You don't organize anything. You just talk."
> Show what the chat looks like. One screenshot of a brain dump → AI response. That's the pitch.
> User lands at 2am in an ADHD hyperfocus research spiral → don't lose them with a wall of text.

**What to build:**
- The hero should show the chat interface in action, not describe features in text
- A demo interaction — could be:
  - An animated sequence showing a brain dump → AI response → "what should I do?" → one item
  - A static screenshot/mockup of a real conversation
  - CSS-animated chat bubbles that play out a scenario
- Keep the pitch emotional, not feature-driven. Target audience: "I've tried everything and nothing works"
- Price must be visible: free (10 msgs/day), $8/month unlimited
- Single CTA: "try it" or "get started" — not "learn more"
- Must work on mobile (most ADHD users browse on phones, often in bed)

**Design constraints from FRONTEND_SPEC.md:**
- Background: dark (#0D0D0F warm gray range)
- Font: Satoshi Variable (self-hosted)
- Accent: muted teal/dusty sage (#5dcaa5 is current accent)
- No component library — custom components
- Glass morphism on interactive elements
- Animations: spring easing, subtle not flashy

**Read `docs/PRODUCT_SPEC.md` "The Problem" section** — the landing page should mirror the language there. These users have experienced the "productivity tool failure cycle" — the landing page should acknowledge that.

**Read `docs/CHAT_INTERACTIONS.md`** — pick 1-2 of the interaction examples to base the demo on. The brain dump example (#2) or the "what should I do?" example (#3) are the strongest demos.

### 1.2 Routing refinement

**Current state:** `frontend/src/App.tsx:12-29` — `isStandalone()` detects PWA mode, skips landing page.

- Browser visitors: LandingPage → click CTA → LoginScreen → ChatScreen
- PWA (standalone): LoginScreen → ChatScreen (skip landing)
- Already authenticated: straight to ChatScreen

This routing is correct. Make sure the landing page CTA transitions smoothly (View Transitions API is already set up in App.tsx:117-121).

---

## 2. UI Polish (Phase 2C)

### 2.1 Animation and responsive fixes

**Current state:** `frontend/src/styles/globals.css` has animation variables (spring easing, durations) and glass morphism variables. Component-specific animations are inline.

**Things to check and fix:**
- Message entrance animations — should be 250ms spring easing with translateY(12px) + scale(0.97). User messages from bottom-right
- Action buttons — stagger 80ms after parent message entrance
- Typing indicator — gentle pulse, not bouncy
- Send button — subtle scale on press
- Voice recording — expanding ring animation
- Test on a real phone early — don't build desktop-first
- `overscroll-behavior: none` on message container (prevents rubber-band bounce)
- `env(safe-area-inset-bottom)` on input bar (iPhone notch/home bar)
- Max message width ~70% so long messages don't stretch edge-to-edge
- On desktop: chat area centered with max-width ~600-700px

**Files:**
- `frontend/src/styles/globals.css` — variables and base styles
- `frontend/src/components/MessageBubble.tsx` — message animations
- `frontend/src/components/ActionButtons.tsx` — stagger animations
- `frontend/src/components/InputBar.tsx` — send/mic button animations

### 2.2 Concurrent message handling

**Current state:** `frontend/src/components/ChatScreen.tsx` has a queue system (lines 76-155). If user sends while AI is streaming, messages queue and flush sequentially with 500ms delay.

**What to polish:**
- Visual state for queued/pending messages — show a clock icon or subtle opacity difference
- Message ordering guarantees — queued messages must appear in the order sent
- If user sends while offline, messages queue (this works). When back online, they flush (this works). But the queue is volatile — lost on page reload
- Consider persisting the queue to localStorage so messages survive refresh

**Files:**
- `frontend/src/components/ChatScreen.tsx` — queue logic
- `frontend/src/components/MessageBubble.tsx` — pending state visual

### 2.3 Offline message queuing persistence

**Current state:** `frontend/src/hooks/useOffline.ts` tracks `navigator.onLine`. `ChatScreen.tsx` queues messages in React state when offline. Queue is lost on page reload.

**What to add:**
- Persist queued messages to localStorage
- On app load, check localStorage for queued messages and flush them
- Show "sending..." state for messages being flushed from storage
- Clear from localStorage once confirmed sent

**Files:**
- `frontend/src/components/ChatScreen.tsx` — queue persistence
- `frontend/src/lib/api.ts` — possibly add retry logic for failed sends

### 2.4 PWA install prompt

**Current state:** No in-app install prompt. `usePush.ts` handles push notification permission (after 6 messages) but not PWA install.

**What to build:**
- After 3+ interactions, show a subtle in-chat system message: "tip: add unspool to your home screen for the best experience"
- On Android: capture the `beforeinstallprompt` event, show it when appropriate
- On iOS: detect Safari + not standalone, show brief instructions ("tap Share → Add to Home Screen")
- On desktop: show if `beforeinstallprompt` is available
- Only show once — persist dismissal to localStorage
- Not a modal, not a banner — a system message in the chat flow

**Detection:**
- Already standalone → don't show
- Android Chrome → `beforeinstallprompt` event
- iOS Safari → `navigator.standalone === undefined && /iP(hone|ad)/.test(navigator.userAgent)`
- Desktop → `beforeinstallprompt` event

**Files:**
- Create `frontend/src/hooks/usePWAInstall.ts` — detect platform, manage prompt state
- `frontend/src/components/ChatScreen.tsx` — inject system message

---

## 3. Testing (Phase 2B)

### 3.1 Frontend testing setup

**Current state:** No test framework. No test files. `package.json` has no test dependencies.

**What to set up:**
- Add `vitest` + `@testing-library/react` + `jsdom` to dev dependencies
- Configure in `vite.config.ts` (vitest integrates natively with Vite)
- Add `"test": "vitest run"` script to package.json

**Critical paths to test first:**
- `api.ts` SSE stream parsing — mock fetchEventSource, verify token/actions/done events parse correctly
- `useAuth.ts` — auth state transitions (loading → authenticated → unauthenticated)
- `ChatScreen.tsx` — message send → streaming → message appears in list
- `useOffline.ts` — online/offline state changes

**Files:**
- `frontend/vite.config.ts` — add vitest config
- `frontend/package.json` — add test deps + script
- Create `frontend/src/__tests__/` directory
- Create test files: `api.test.ts`, `useAuth.test.ts`, `ChatScreen.test.tsx`, `useOffline.test.ts`

---

## 4. Accessibility (Phase 4)

### 4.1 Accessibility pass

**Current state:** Some accessibility exists — `MessageList.tsx` has `aria-live="polite"`, `OfflineBanner.tsx` has `role="alert"`, `ActionButtons.tsx` has `role="group"`. But no systematic audit.

**What to check and fix:**

**Keyboard navigation:**
- Tab through all interactive elements in logical order
- Enter/Space activates buttons
- Escape closes any overlays
- Focus management when messages load (don't trap focus)

**Screen reader:**
- All buttons have `aria-label` (mic button, send button, stop button, action buttons)
- Message role announced ("you said..." / "assistant said...")
- Streaming state announced (aria-live region updates)
- Loading states announced

**Visual:**
- Run Lighthouse accessibility audit — target score 90+
- Check color contrast ratios (WCAG AA: 4.5:1 for normal text, 3:1 for large text)
- Current text (#e0e0e0) on background (#0c0a1f) — verify this passes
- Error states (#c4736d) must also have sufficient contrast
- Focus indicators visible on all interactive elements (`:focus-visible` styles)

**Motion:**
- `prefers-reduced-motion` media query — already referenced in globals.css. Verify ALL animations respect it (message entrance, typing indicator, recording animation, view transitions)
- Reduce or remove: spring animations, sliding transitions, pulsing indicators

**Files:**
- `frontend/src/styles/globals.css` — focus styles, reduced motion
- `frontend/src/components/InputBar.tsx` — aria-labels on buttons
- `frontend/src/components/MessageBubble.tsx` — role, aria attributes
- `frontend/src/components/MessageList.tsx` — aria-live regions
- `frontend/src/components/VoiceInput.tsx` — recording state announcement

---

## Verification

After each group of changes:

```bash
# Build succeeds
cd frontend && npm run build

# Tests pass (after testing setup)
cd frontend && npm run test

# Format check
cd frontend && npx prettier --check src/

# Manual checks:
# - Open on mobile (real phone, not just devtools)
# - Test landing page on slow 3G (devtools throttling)
# - Test offline → online transition
# - Test PWA install flow on Android + iOS
# - Run Lighthouse (Performance, Accessibility, PWA scores)
```

---

## Files modified (for merge conflict awareness)

**New files:**
- `frontend/src/hooks/usePWAInstall.ts`
- `frontend/src/__tests__/api.test.ts`
- `frontend/src/__tests__/useAuth.test.ts`
- `frontend/src/__tests__/ChatScreen.test.tsx`
- `frontend/src/__tests__/useOffline.test.ts`

**Modified files:**
- `frontend/src/components/LandingPage.tsx` (major rewrite)
- `frontend/src/components/ChatScreen.tsx` (queue persistence, install prompt)
- `frontend/src/components/InputBar.tsx` (animations, aria)
- `frontend/src/components/MessageBubble.tsx` (animations, pending state, aria)
- `frontend/src/components/MessageList.tsx` (aria-live)
- `frontend/src/components/ActionButtons.tsx` (stagger animation)
- `frontend/src/components/VoiceInput.tsx` (aria)
- `frontend/src/hooks/useOffline.ts` (persistence)
- `frontend/src/lib/api.ts` (retry logic)
- `frontend/src/styles/globals.css` (animations, focus, reduced motion)
- `frontend/src/App.tsx` (routing polish)
- `frontend/vite.config.ts` (vitest)
- `frontend/package.json` (test deps)

**Not touched:** `backend/*`, `.github/*`, `.pre-commit-config.yaml` (owned by devops session)
