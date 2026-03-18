# Frontend Fixes & Improvements

Comprehensive plan for frontend UI/UX improvements. Covers bug fixes, ADHD-friendly polish, first-person thought UI prototype, design tooling, and native app strategy.

---

## Part A: Bug Fixes (Priority)

### A1. Chat history lost on login/refresh

**Problem:** Every time you log in or refresh the page, chat history is gone. You always see the welcome message instead of your previous conversations.

**Root cause:** The backend `GET /api/messages` returns a wrapped object:
```json
{"messages": [...], "has_more": true}
```

But the frontend `fetchMessages()` in `frontend/src/lib/api.ts` (line 111) treats the raw response as an array:
```ts
return (await response.json()) as Message[]
```

This means `fetched` is actually `{messages: [...], has_more: bool}`, not an array. When `App.tsx` (line 95) checks `fetched.length > 0`, it gets `undefined` (objects don't have `.length`), so it always falls through to showing the welcome message.

**Fix:** In `frontend/src/lib/api.ts`, unwrap the response:
```ts
const data = (await response.json()) as { messages: Message[]; has_more: boolean }
return data.messages
```

**Files:**
- `frontend/src/lib/api.ts` — fix `fetchMessages` return value
- `frontend/src/App.tsx` — no changes needed once api.ts is fixed

**Also check:** The field name mapping between backend and frontend. Backend returns `created_at` (snake_case) but the frontend `Message` type uses `createdAt` (camelCase). If asyncpg returns snake_case, we also need a mapping step:
```ts
return data.messages.map(m => ({
  ...m,
  createdAt: m.created_at || m.createdAt,
}))
```
Verify by logging the actual response in the browser console.

**Priority:** Critical. Without this, the app has no memory between sessions — the core value prop is broken.

---

### A2. Enter key — add Shift+Enter hint

**Problem:** Pressing Enter sends the message. Users can use Shift+Enter for newlines, but there's no indication this works. For a brain-dump app, multi-line input is essential.

**Current behavior in `frontend/src/components/InputBar.tsx` (line 40):**
```ts
if (e.key === 'Enter' && !e.shiftKey) {
  e.preventDefault()
  handleSend()
}
```

Shift+Enter already works (the `!e.shiftKey` guard lets it through). Users just don't know about it.

**Fix:** Keep Enter = send. Add a subtle hint on desktop:
1. Small muted text "shift+enter for new line" below the textarea
2. Only visible when textarea has focus and is empty
3. Fades out permanently after first Shift+Enter use (store flag in `localStorage`)
4. Don't show on mobile (detect via `'ontouchstart' in window` or media query)

The `TextareaAutosize` component already supports 1-4 rows, so multi-line rendering works once users know about Shift+Enter.

**Files:**
- `frontend/src/components/InputBar.tsx` — add hint element + localStorage logic
- `frontend/src/components/InputBar.css` — style the hint text

---

### A3. Streaming feels janky — not word-by-word

**Problem:** AI responses appear in chunks rather than smooth word-by-word streaming. Text jumps in bursts instead of flowing.

**Root cause analysis — the streaming path:**
1. Backend: `async for token in execute_pipeline()` yields SSE event `{"type":"token","content":"..."}` — `backend/src/api/chat.py` (line 125-127)
2. Frontend: `fetchEventSource` receives each SSE event → `onToken(parsed.content)` → `accumulated += t` → `setStreamingContent(accumulated)` — `frontend/src/lib/api.ts` (line 66), `frontend/src/components/ChatScreen.tsx` (line 287-292)
3. Render: `<StreamingText content={streamingContent}>` → `<Markdown>{content}</Markdown>` — `frontend/src/components/StreamingText.tsx`

**Two problems:**
- **Every token triggers a full Markdown re-parse.** `markdown-to-jsx` re-parses the entire accumulated string on every `setStreamingContent` call. As responses get longer, this gets progressively more expensive — O(n) work on every token.
- **Tokens arrive in bursts.** The LLM API and SSE buffering can batch multiple tokens into rapid-fire events, causing visual jumps instead of smooth flow.

**Fix (two parts):**

**Part 1 — RAF-debounced rendering:** Instead of calling `setStreamingContent` on every single token, accumulate tokens in a ref and flush to React state via `requestAnimationFrame`. This batches updates to 60fps max instead of potentially hundreds of re-renders per second.

```ts
// In ChatScreen.tsx onToken callback:
const accumulatedRef = useRef('')
const rafPendingRef = useRef(false)

onToken: (t) => {
  accumulatedRef.current += t
  if (!rafPendingRef.current) {
    rafPendingRef.current = true
    requestAnimationFrame(() => {
      setStreamingContent(accumulatedRef.current)
      rafPendingRef.current = false
    })
  }
}
```

**Part 2 — Plain text during streaming, Markdown on completion:** While tokens are arriving, render as plain text with `white-space: pre-wrap`. When the stream completes, the message gets added to the `messages` array and renders through `MessageBubble` which already uses `<Markdown>`. This eliminates the O(n) re-parse on every frame.

In `frontend/src/components/StreamingText.tsx`:
```tsx
<div className="streaming-text">
  <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
  <span className="streaming-cursor" />
</div>
```

**Files:**
- `frontend/src/components/ChatScreen.tsx` — RAF-debounced token accumulation (both `handleSend` and `flushQueue` callbacks)
- `frontend/src/components/StreamingText.tsx` — remove `<Markdown>`, use plain text during streaming

---

### A4. Demo text boxes — inconsistent text alignment

**Problem:** On the landing page, some demo chat bubbles have center-aligned text, others have left-aligned text. Looks broken.

**Root cause:** `.demo-bubble` in `frontend/src/components/ChatDemo.css` doesn't set `text-align` explicitly. The parent `.demo-message-row` uses `align-items: flex-start/flex-end` for horizontal bubble positioning, but text alignment inside short bubbles can inherit differently depending on content width and flex layout.

**Fix:** Add `text-align: left` to `.demo-bubble` in `frontend/src/components/ChatDemo.css`.

Also verify the content rendering in `frontend/src/components/ChatDemo.tsx` (line 292-294) — it splits on `\n` into `<p>` tags, each of which should inherit left alignment.

**Files:**
- `frontend/src/components/ChatDemo.css` — add `text-align: left` to `.demo-bubble`

---

### A5. Cat silhouette barely visible — remove

**Problem:** The static cat silhouette sitting on the hills SVG (on both landing page and login screen) is `fill="rgba(0,0,0,0.5)"` on a near-black hill — virtually invisible.

**Files:**
- `frontend/src/components/LandingPage.tsx` (lines 70-82) — cat SVG group in landing hills
- `frontend/src/components/LoginScreen.tsx` (lines 89-109) — cat SVG group in login hills

**Fix:** Remove both `<g>` elements containing the cat silhouettes from the hill SVGs. They're too small and too dark to serve any purpose.

---

### A6. Cat easter egg — redesign with better animation

**Problem:** Current cat easter egg (`frontend/src/components/CatEasterEgg.tsx`) has 3 variants (hopper/observer/peek) but they're tiny SVGs (24-30px) at `opacity: 0.6` in `color: var(--color-text-muted)` — barely noticeable even when they trigger.

**Redesign:** A single, higher-quality cat animation in the starfield/background:
- Larger cat silhouette (~60-80px) that jumps across the bottom of the screen
- Uses muted starfield color palette (not accent color), something like `#2a2450` to `#3d3570`
- Lower opacity (0.15-0.25) — visible but ambient, doesn't compete with chat content
- Parabolic arc trajectory — more playful, more cat-like than a linear walk
- Optional: tiny star particles where paws "land"
- Tail has its own secondary animation (trailing, slight sway)
- Duration: ~3 seconds for the jump arc

**Consider:** Using a Lottie animation (via `lottie-react`) instead of hand-coded SVG. Buy a cat animation pack from Creattie or LottieFiles ($15-50) for much higher quality than hand-drawn SVG paths. Or generate with Gemini/Claude and iterate.

**Trigger adjustments:** Keep current logic (6+ messages, 5% chance, 5-min cooldown) but bump probability to 8-10% since the animation is more subtle.

**Files:**
- `frontend/src/components/CatEasterEgg.tsx` — replace SVG and component
- `frontend/src/components/CatEasterEgg.css` — replace animations with parabolic arc
- `frontend/src/hooks/useCatEasterEgg.ts` — adjust trigger probability

**Note:** Creative/design task. Prototype separately and iterate visually before committing.

---

## Part B: First-Person Thought UI (Prototype)

### The concept

Instead of a chatbot that talks TO you ("I'll remind you about the dentist"), the UI simulates your own mind talking ("dentist — should call during lunch, before the cleaning appointment expires").

This isn't a conversation between two parties. It's a stream of your own thoughts — some typed by you, others surfaced by your mind.

### Decision: Prototype both modes

Build first-person as a toggleable mode alongside the current chatbot layout. Let early users try both and see which resonates.

**Implementation:** Add `uiMode: 'chat' | 'thought'` to a React context (or just localStorage + state). The toggle can be a subtle button in the chat header or a settings option. Both modes share the same data/streaming infrastructure — only the rendering layer changes.

### What changes in first-person mode

**B1. Single-column layout (no left/right split)**

Current: user messages align right, AI messages align left (classic chatbot two-column).

First-person: everything flows in one direction. No left/right split. All content aligns left, like a journal or inner monologue.

- Remove `justify-content: flex-end` from `.message-row.user`
- Both user and AI messages align left
- Differentiate by subtle visual treatment, not position:
  - **Your input** (what you typed): slightly brighter text, thin left border in accent color
  - **Your mind** (AI responses): standard text, no border — this is the "default" voice

**Files:** `frontend/src/components/MessageBubble.css`, `frontend/src/components/MessageBubble.tsx`

**B2. Remove glass bubble styling from AI messages**

The glass morphism bubble says "this is a separate entity talking to you." In first-person mode, AI responses should feel like thoughts floating in space — no border, no background, just text against the sky.

- **User input**: keep a subtle bubble (you typed this, it's an action)
- **AI response**: no bubble, no border. Just text with generous padding. Maybe a very faint left-edge glow instead.

**B3. Change the thinking indicator**

Current: three dots in a glass bubble — reads as "someone else is typing."

First-person options:
- A gentle ellipsis "..." with slow opacity pulse
- A single breathing dot
- Just the blinking streaming cursor (no dots at all)

**B4. Placeholder text**

Current: "what's on your mind?" — already works for both chatbot and first-person. Keep it.

**B5. Rewrite demo sequences**

Current demo text (`frontend/src/components/ChatDemo.tsx`):
```
User: "I need to call the dentist, my lease renewal is due friday..."
AI: "got all five. lease renewal — friday, I'll bring this up wednesday..."
```

First-person version:
```
[you type]: "dentist, lease renewal friday, plant watering idea, text sarah, car registration?"
[your mind]: "lease renewal — friday. surfacing wednesday.
dentist — during business hours tomorrow.
text sarah — quick one, now?
car registration — checking.
plant watering — idea saved."
```

The AI voice drops "I" — it doesn't refer to itself. Terse, like inner speech. No "I'll", no "got all five." Just clarity.

**B6. Aria labels**

Current: `"Unspool said: ..."` — change to `"Your thought: ..."` or just the content without role attribution.

### What stays the same in first-person mode
- Glass morphism on user input bubbles
- Starfield background
- Action buttons (already minimal)
- Input bar design
- Accent color
- Cat animation
- All technical infrastructure (SSE, offline queue, etc.)

### Open questions (resolve during prototyping)
- **Errors:** "couldn't reach the server" feels wrong as inner speech. Errors likely stay third-person — they're system events, not thoughts.
- **System messages:** PWA install prompt, etc. — clearly the app talking. Stay third-person in both modes.
- **Demo sequences:** Need first-person versions for the landing page when showing that mode.

---

## Part C: ADHD-Friendly Polish

CSS and small behavior changes based on ADHD-friendly UI research. All of these can be done in a single pass.

### C1. Warmer text color
**File:** `frontend/src/styles/globals.css`
```
--color-text-primary: #e0e0e0  →  #E8E4E0
```
Pure gray reads cold/clinical. Warm off-white (#E8E4E0) reduces eye strain and feels more personal. Research shows warmer tones increase reading comfort in dark themes.

### C2. Increase message font size
**File:** `frontend/src/components/MessageBubble.css`
```
font-size: 0.9375rem (15px)  →  1rem (16px)
```
15px is readable but slightly small for a primary reading surface. 16px reduces cognitive effort.

### C3. Increase line-height + letter-spacing
**File:** `frontend/src/components/MessageBubble.css`
```
line-height: 1.5  →  1.6
letter-spacing: 0.01em  (add)
```
More breathing room between lines reduces visual crowding. ADHD research recommends 1.5-1.8 line-height. Slight letter-spacing (0.01em) improves character discrimination — imperceptible visually but measurable in readability studies.

### C4. More paragraph spacing in AI messages
**File:** `frontend/src/components/MessageBubble.css`
```
.markdown-content p + p { margin-top: 0.6em  →  0.85em }
```
AI responses can be multi-paragraph. More spacing creates clear visual chunks, making it easier to track your place in a response.

### C5. Auto-save draft to localStorage
**File:** `frontend/src/components/InputBar.tsx`
- On `value` change (debounced 500ms), save to `localStorage` key `unspool-draft`
- On component mount, restore from `unspool-draft`
- On successful send, clear `unspool-draft`
- Zero-UI feature — no indicator, it just works

ADHD users get interrupted constantly. Losing a half-typed message to a tab switch or accidental refresh is frustrating. This prevents that silently.

### C6. Calmer typing indicator
**File:** `frontend/src/components/TypingIndicator.css`
- Slow the cycle: `1.4s → 2s`
- Reduce peak opacity: `0.8 → 0.6`
- Raise base opacity: `0.3 → 0.35`

Current pulsing dots create subconscious urgency. A slower, subtler pulse says "I'm thinking, take your time." Pi.ai uses a similar calmer indicator.

### C7. Softer error color
**File:** `frontend/src/styles/globals.css`
```
--color-error: #c4736d  →  #c4877f
```
Push error color slightly more toward salmon. Errors aren't the user's fault — they should feel like "oops" not "ERROR."

Also in `frontend/src/components/MessageBubble.css`, error border:
```
rgba(196, 115, 109, 0.3)  →  rgba(196, 135, 127, 0.25)
```

### C8. Brighter secondary text
**File:** `frontend/src/styles/globals.css`
```
--color-text-secondary: #888  →  #999
```
#888 on dark background has marginal contrast. #999 improves readability of timestamps without competing with primary text. Helps meet WCAG AA.

### C9. Increase message gap
**File:** `frontend/src/styles/globals.css`
```
--spacing-message-gap: 14px  →  16px
```
More whitespace between messages reduces visual density. Each message feels like its own thought.

---

## Part D: Design Tooling & Resources

Tools for achieving a professional look without design background.

**For prototyping layouts:**
- **v0.dev** — describe the UI in words, get production React + Tailwind code. Free tier available. Great for rapid layout exploration of first-person vs chatbot modes.
- **Figma** — BRIX Mobile Chat UI Kit (free, 150+ components) for reference patterns.

**For animation quality:**
- **Motion** (framer-motion successor) — `npm install motion`. 330+ pre-built animations, spring physics, scroll-linked effects. Would level up message entrances, streaming cursor, and transitions.
- **Lottie** for cat animation — buy from Creattie or LottieFiles ($15-50), integrate via `lottie-react`. Tiny file sizes (JSON), 60fps, way higher quality than hand-coded SVG. IconScout has cat-specific packs.

**For glass morphism refinement:**
- **Glass UI** (ui.glass/generator) — visual CSS generator for exact glass parameters.

**For streaming/chat infrastructure:**
- **Assistant-UI** (assistant-ui.com) — open-source React library for AI chat. Composable primitives for streaming, markdown, attachments. Could replace hand-rolled StreamingText/MessageBubble with battle-tested components. Worth evaluating before building first-person mode from scratch.

---

## Part E: Native App Strategy

**Current recommendation: PWA first, native later.**

| Step | When | What | Cost |
|------|------|------|------|
| 1. PWA | Now | Already done — ship and validate | $0 |
| 2. Android | After first paying users | TWA via PWABuilder, 30 mins, zero code changes | $25 one-time |
| 3. iOS | After revenue justifies it | Capacitor wrapper with native push | $99/year |

**Why not now:**
- PWA "Add to Home Screen" on Android already gives a full-screen app experience
- iOS bare WebView wrappers get rejected ~80% of the time (Apple Guideline 4.2)
- Capacitor for iOS takes ~2 weeks and requires native push notification setup (Firebase/APNs)
- Better to validate the product on web first, then add store presence for credibility + discoverability

**Android path (trivial):**
- Use PWABuilder or Bubblewrap to package PWA for Google Play
- Zero code changes — point at your PWA URL, it generates the APK
- Google Play account: $25 one-time
- Review: ~48 hours, rarely rejects well-formed PWAs

**iOS path (requires work):**
- Bare WebView wrapper will be rejected (~80% rate, Apple Guideline 4.2)
- Use Capacitor (`npm install @capacitor/core @capacitor/cli`) to wrap React app with native shell
- Add Capacitor Push Notifications plugin for native push (replaces/augments Service Worker push)
- Native push significantly improves iOS approval odds
- Setup: ~2-5 hours for basic, plus push notification integration

**When to reconsider:** When you have paying customers asking "is this on the App Store?"

---

## Summary of All Changes by File

| File | Changes |
|------|---------|
| `frontend/src/lib/api.ts` | **[CRITICAL]** Fix fetchMessages to unwrap `{messages: [...]}` response |
| `frontend/src/components/InputBar.tsx` | Add Shift+Enter hint on desktop; auto-save draft to localStorage |
| `frontend/src/components/InputBar.css` | Style for the shift+enter hint |
| `frontend/src/components/ChatScreen.tsx` | RAF-debounced streaming token updates |
| `frontend/src/components/StreamingText.tsx` | Plain text during streaming (remove Markdown re-parse) |
| `frontend/src/components/ChatDemo.css` | Fix text-align on demo bubbles |
| `frontend/src/components/ChatDemo.tsx` | Update demo sequences for first-person mode |
| `frontend/src/components/LandingPage.tsx` | Remove static cat SVG from hills |
| `frontend/src/components/LoginScreen.tsx` | Remove static cat SVG from hills |
| `frontend/src/components/CatEasterEgg.tsx` | Redesign: larger jumping cat silhouette (or Lottie) |
| `frontend/src/components/CatEasterEgg.css` | New parabolic jump animation |
| `frontend/src/hooks/useCatEasterEgg.ts` | Adjust trigger probability (5% to 8-10%) |
| `frontend/src/styles/globals.css` | Warmer text (#E8E4E0), softer error (#c4877f), brighter secondary (#999), message gap (16px) |
| `frontend/src/components/MessageBubble.css` | Font 16px, line-height 1.6, letter-spacing 0.01em, paragraph spacing 0.85em, softer error border; first-person layout |
| `frontend/src/components/MessageBubble.tsx` | First-person mode: aria labels, layout changes |
| `frontend/src/components/TypingIndicator.css` | Slower calmer pulse (2s cycle, 0.35-0.6 opacity) |

---

## Suggested Sprint Order

1. **A1** (chat history fix) — critical bug, everything else is meaningless without persistence
2. **A2** (enter key hint) + **A4** (demo alignment) — quick wins
3. **A3** (streaming fix) — noticeable quality bump
4. **C1-C9** (ADHD polish) — all CSS changes, one pass
5. **A5** (remove static cats) + **A6** (new cat animation) — creative work, prototype separately
6. **B1-B6** (first-person UI) — biggest change, needs prototyping and user testing

---

## Verification Checklist

1. `cd frontend && npm run dev` — visual check at localhost:5173
2. Login, send messages, refresh page — verify chat history persists
3. Login, sign out, sign back in — verify history is still there
4. Type multi-line message with Shift+Enter on desktop — verify newlines work + hint appears
5. Trigger AI response — verify smooth word-by-word streaming (no chunky jumps)
6. Check landing page demo — verify all demo text is left-aligned in bubbles
7. Verify static cat removed from login + landing page hills
8. Wait for cat animation trigger — verify it's visible and smooth
9. Toggle first-person mode — verify layout changes correctly
10. Mobile viewport (375px) — verify no layout issues
11. `prefers-reduced-motion: reduce` in dev tools — verify all animations disabled
12. Check contrast: #999 secondary text against darkest background (#0c0a1f) meets WCAG AA
