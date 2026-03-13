# Unspool — Frontend Specification

**For:** Claude Code / Cursor / AI code generation  
**Stack:** React + Vite + TypeScript  
**Output:** Progressive Web App (PWA) deployable to Vercel/Cloudflare Pages  
**Design Philosophy:** Brutally minimal. Calm. Anti-productivity-app. A quiet room, not a command center.

---

## Overview

Unspool is a single-screen PWA. The entire app is one fullscreen chat interface. There are no other pages, no navigation, no sidebar, no settings. The chat IS the app.

Think: iMessage with one contact, fullscreen, dark theme, nothing else.

---

## Screens (there are only 3)

### 1. Login Screen
- Clean, centered layout on dark background
- App name "unspool" in subtle, muted text above the login area (not a loud logo — just the word)
- Tagline beneath: "let your mind unspool" in smaller muted text
- Primary action: **"continue with Google"** button (large, prominent, full-width within the centered container). This triggers Supabase Google OAuth with `calendar.readonly` scope included. One consent screen covers sign-in AND calendar access.
- Below the Google button, smaller muted text: **"or continue with email"** — tapping this reveals an email input field + "send link" button. Triggers Supabase magic link flow.
- After magic link sent: message appears — "check your email for a magic link"
- No password field ever. No "sign up" vs "log in" distinction. No Apple/GitHub/Facebook OAuth.
- Google consent screen will say: "Unspool wants to: view your email address, sign you in, and view your calendar events." User taps Allow once, never asked again.
- If user signs in via magic link (no Google), calendar is not connected. The AI will offer to connect it later via in-chat prompt after a few days of use.
- This screen should feel like a door, not a gate. Minimal, calm, two paths but the choice is obvious.

### 2. Chat Screen (the main and only screen)
- Fullscreen chat interface
- Message area takes up full height minus input bar
- Input bar pinned to bottom
- No header bar, no navigation, no hamburger menu
- On first ever open (new user): a single welcome message from the AI already in the chat:
  "hey — dump anything on me. tasks, ideas, deadlines, random thoughts. I'll sort it out."
- On returning: loads recent conversation history (last ~50 messages)

### 3. Payment Screen (inline, not a separate page)
- When user hits rate limit, the AI's response IS the payment prompt
- The message contains a button/link to Stripe checkout
- After payment, a confirmation message appears in chat
- No separate pricing page, billing page, or plan selection screen

---

## Chat Interface — Detailed Spec

### Message Area

**Layout:**
- Messages scroll vertically, newest at bottom
- User messages aligned RIGHT, AI messages aligned LEFT
- Auto-scroll to bottom on new message
- Smooth scroll behavior
- Pull up to load older messages (lazy load history)

**User messages:**
- Subtle background color (muted, not bright)
- Rounded corners
- No avatar, no timestamp visible by default
- Timestamp appears on tap/hover (small, muted text)

**AI messages:**
- Different subtle background color or no background (just text)
- Rounded corners
- No avatar, no bot icon, no "AI" label — it's just the other side of the conversation
- Streaming: text appears word by word / chunk by chunk as it arrives from the API
- While streaming: subtle blinking cursor at the end of the message
- After streaming complete: cursor disappears

**Streaming behavior (critical):**
- Use Server-Sent Events (SSE) or fetch with ReadableStream
- Each token/chunk appends to the current AI message in real-time
- The message bubble grows as text arrives
- Scroll follows the growing message automatically
- User can still scroll up while AI is responding (scroll lock disengages)
- If user scrolls up during streaming, show a "↓ new message" pill at the bottom to jump back

**Typing indicator:**
- Before first token arrives: show a subtle animated indicator (3 dots pulsing, or a minimal wave)
- Replaces with actual text once streaming begins
- Duration: typically 200-500ms before first token arrives

### Input Bar

**Layout:**
- Pinned to bottom of screen, always visible
- Full width with padding
- Text input field (auto-expanding, multiline — grows with content up to ~4 lines, then scrolls internally)
- Microphone button (left or right of input)
- Send button (right side, only visible when there's text)

**Text input:**
- Placeholder: "what's on your mind?" (not "Type a message...")
- Auto-focus on app open
- Submit on Enter (desktop), Shift+Enter for new line
- On mobile: respects virtual keyboard (input bar pushes up above keyboard, not hidden behind it)
- Clear input after send
- Disable while AI is streaming (prevent double-sends)

**Send button:**
- Only appears when input has text (not visible when empty, microphone shows instead)
- Subtle animation on tap
- Disabled + loading state while waiting for response

**Microphone / Voice Input button:**
- Visible when text input is empty
- On tap: begins recording using Web Speech API (SpeechRecognition) or Whisper API
- Visual feedback while recording:
  - Microphone icon changes state (pulsing, color change, or waveform animation)
  - Small waveform or pulse animation near the input bar
  - Clear "recording" state that's obviously different from idle
- On stop (tap again or silence detection):
  - Transcribed text appears in the input field (user can review/edit before sending)
  - NOT auto-sent — user sees the transcript first and taps send
  - This is important: ADHD users ramble, they need to see what they said before committing
- If speech recognition fails: subtle error message, fall back to typing
- Silence detection: stop recording after ~3 seconds of silence

### Empty States

**Brand new user (first ever open after login):**
```
AI: hey — dump anything on me. tasks, ideas,
    deadlines, random thoughts. I'll sort it out.
```
That's it. One message. The cursor blinks in the input bar. The user starts typing.

**Returning user with history:**
Load last ~50 messages from conversation history. User sees their previous conversation.

**Returning user, first message of new session:**
No special greeting. The chat just shows previous messages. If something urgent is pending, the AI's first response to whatever the user says will piggyback the nudge (handled by backend, not frontend).

---

## Visual Design

### Aesthetic Direction: "quiet dark room"

This is NOT a bright, cheerful productivity app. It's not neon. It's not glassmorphism. It's not gradient-heavy. It's a calm, dark, quiet space where you dump your thoughts. Think: a journal by lamplight, not a mission control center.

**Theme: Dark by default, no light mode in v0.1**

**Colors:**
- Background: very dark warm gray (not pure black — something like #0D0D0F or #111113)
- Chat area background: same or imperceptibly different
- User message bubble: muted warm tone (dark slate, like #1E1E24 with slight warmth)
- AI message: no bubble, just text on the dark background (or very subtle differentiation)
- Text: off-white (#E0E0E0 or similar — not pure white, that's harsh)
- Accent: one single muted color for interactive elements (send button, links, recording indicator). Pick something calming — muted teal, dusty sage, soft amber. NOT blue (every app is blue).
- Error/warning: muted warm red, not alarming
- Timestamps/secondary text: very muted (#666 range)

**Typography:**
- Body text (messages): clean, readable, ~16px on mobile. Choose something with personality but high readability. NOT Inter, NOT Roboto, NOT system default. Consider: Satoshi, General Sans, Switzer, Cabinet Grotesk, or similar modern geometric sans with warmth.
- Input placeholder: same font, slightly lighter weight
- No headings needed (there's nothing to head)
- Line height: generous (1.5-1.6) for readability

**Spacing & Layout:**
- Generous padding on messages (don't pack them tight)
- Clear visual separation between messages without heavy dividers
- Message gap: ~12-16px between messages
- Side padding: ~16-20px on mobile, more on desktop
- Max message width: ~70% of screen width so long messages don't stretch edge to edge
- On desktop: center the chat area with max-width (~600-700px) so it doesn't stretch across a 27" monitor

**Animations & Motion (subtle, not flashy):**
- New messages: gentle fade-in + slight slide up (100-200ms, ease-out)
- Typing indicator: gentle pulse, not bouncy
- Send button: subtle scale on press
- Microphone recording: gentle pulse glow on the icon
- No page transitions (there's only one page)
- No skeleton loaders — if loading, show the typing indicator
- Scroll behavior: smooth, inertial

**Border & Shadows:**
- Minimal to none. No card shadows, no heavy borders.
- Message bubbles: differentiated by background color only, or extremely subtle border (1px, very low opacity)
- Input bar: subtle top border or shadow to separate from messages, nothing heavy

**Overall Feeling:**
- If someone opens this app at 2am in bed, it should feel comfortable, not blinding
- If someone opens this app during a stressful moment, it should feel calming, not stimulating
- It should look like it was designed by someone with taste, not generated by AI
- It should NOT look like ChatGPT, Claude.ai, or any other AI chat interface. Those are tools. This is a companion.

---

## PWA Configuration

### manifest.json
```json
{
  "name": "Unspool",
  "short_name": "Unspool",
  "description": "Let your mind unspool",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0D0D0F",
  "theme_color": "#0D0D0F",
  "orientation": "portrait",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

### Service Worker
- Cache the app shell (HTML, CSS, JS, fonts) for offline loading
- When offline: show the cached chat UI with a subtle "offline — messages will send when you're back" indicator
- NOT full offline functionality in v0.1 — just graceful degradation

### Push Notifications
- Request permission after first successful conversation (not on first load — that's annoying)
- Use Web Push API with VAPID keys
- Backend triggers push for hard deadline notifications
- Notification content: short, one line, e.g. "rent's due tomorrow"
- Tap notification → opens the app to the chat

---

## Mobile-Specific Behavior

- Input bar moves up when virtual keyboard opens (viewport must resize, not overlap)
- Use `<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">` to prevent zoom on input focus
- Use `env(safe-area-inset-bottom)` for devices with home bar (iPhone notch/bar)
- Touch targets: minimum 44x44px for all interactive elements
- Haptic feedback on send (if available via navigator.vibrate)
- Prevent pull-to-refresh in the chat area (conflicts with scrolling)
- Smooth momentum scrolling on message area

---

## Desktop Behavior

- Chat area centered, max-width ~600-700px
- Subtle background pattern or gradient outside the chat area (very subtle)
- Enter to send, Shift+Enter for newline
- Input auto-focuses on page load
- No special desktop features in v0.1

---

## API Integration Points (frontend needs these)

### POST /api/chat (send message)
```
Request: { message: string, session_id: string }
Response: Server-Sent Events stream
  - Each event: { type: "token", data: "word " }
  - Final event: { type: "done", data: { items_extracted: [...] } }
```

### GET /api/messages (load history)
```
Request: ?limit=50&before=<message_id>
Response: { messages: [{ id, role, content, created_at }] }
```

### POST /api/auth/magic-link (login fallback)
```
Request: { email: string }
Response: { success: true }
(Handled by Supabase client SDK)
```

### Google OAuth (login primary)
```
Handled entirely by Supabase client SDK:
supabase.auth.signInWithOAuth({
  provider: 'google',
  options: {
    scopes: 'https://www.googleapis.com/auth/calendar.readonly',
    redirectTo: window.location.origin
  }
})
Returns: Google access token stored in Supabase session.
Backend uses this token to read Google Calendar events.
```

### POST /api/subscribe (payment)
```
Request: { }
Response: { checkout_url: string }
(Redirect to Stripe checkout, return to chat on success)
```

These are the interfaces the frontend calls. The backend implementation is separate.

---

## State Management (minimal)

- **Auth state:** is user logged in? Google or magic link? Calendar connected? (from Supabase session)
- **Messages:** array of { id, role, content, created_at, streaming? }
- **Input text:** current value of the text field
- **Is streaming:** boolean, is AI currently responding?
- **Is recording:** boolean, is microphone active?
- **Session ID:** persistent per user
- **Has calendar:** boolean, did user sign in via Google (calendar available)?

No global state management library needed. React useState/useContext is sufficient.
No Redux, no Zustand, no MobX. This app has ~5 pieces of state.

---

## Accessibility

- All interactive elements keyboard accessible
- Screen reader labels on microphone button, send button
- Sufficient color contrast (WCAG AA minimum)
- Reduced motion: respect `prefers-reduced-motion` media query (disable animations)
- Focus visible on input field
- Aria-live region on message area for screen reader announcements of new messages

---

## File Structure (suggested)

```
unspool/
├── public/
│   ├── manifest.json
│   ├── sw.js                 # Service worker
│   ├── icon-192.png
│   └── icon-512.png
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # Router (login vs chat)
│   ├── components/
│   │   ├── LoginScreen.tsx   # Google OAuth + magic link fallback
│   │   ├── ChatScreen.tsx    # Main chat layout
│   │   ├── MessageList.tsx   # Scrollable message area
│   │   ├── MessageBubble.tsx # Single message (user or AI)
│   │   ├── InputBar.tsx      # Text input + mic + send
│   │   ├── VoiceInput.tsx    # Microphone recording logic
│   │   ├── TypingIndicator.tsx
│   │   └── StreamingText.tsx # Handles token-by-token rendering
│   ├── hooks/
│   │   ├── useChat.ts        # Send message, handle streaming
│   │   ├── useAuth.ts        # Supabase auth (Google OAuth + magic link)
│   │   ├── useVoice.ts       # Speech recognition (swappable provider)
│   │   ├── useCalendar.ts    # Fetch Google Calendar events via backend
│   │   └── usePush.ts       # Push notification setup
│   ├── lib/
│   │   ├── supabase.ts       # Supabase client init
│   │   └── api.ts            # Backend API calls
│   ├── styles/
│   │   └── globals.css       # CSS variables, base styles
│   └── types/
│       └── index.ts          # TypeScript types
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
└── README.md
```

---

## Known Platform Issues & Mitigations

### Mobile Safari (iOS)

These are the most common PWA pain points. All have known solutions:

| Issue | Mitigation |
|---|---|
| `100vh` includes the URL bar, so content hides behind it | Use `100dvh` (dynamic viewport height) everywhere instead of `100vh` |
| Virtual keyboard pushes content up unpredictably | Use `visualViewport` API to detect keyboard height and adjust input bar position |
| Auto-zoom on input focus when font-size < 16px | Ensure all input fields use `font-size: 16px` minimum |
| Rubber-band bounce scroll conflicts with chat scroll | Apply `overscroll-behavior: none` on the message container |
| No "install app" browser prompt like Android | Add a subtle in-chat hint after first conversation: "tip: add to home screen for the best experience" with brief instructions. Don't make it a modal or banner. |
| Push notifications only work when installed to home screen | Detect if running in browser vs standalone mode. If browser: mention home screen install. If standalone: request push permission. |
| Push notifications less reliable than native | Acceptable for v0.1. Plan Capacitor native wrapper for v0.3. |
| Safe area insets (notch, home bar) | Use `env(safe-area-inset-bottom)` on input bar padding |

### Firefox Mobile

Firefox on Android dropped PWA install support. The app works as a website but can't be installed and won't receive push notifications. This affects a small percentage of users. No mitigation needed for v0.1 — just don't break the basic chat experience.

### Cross-Browser Rendering

The chat interface uses only standard CSS (flexbox, custom properties, basic transitions). No exotic features. It will render consistently across Chrome, Safari, Firefox, and Edge. Test on a real phone within the first hour of development — don't build desktop-first.

### Push Notification Compatibility Matrix

| Platform | Install | Push | Reliability |
|---|---|---|---|
| Android Chrome | ✅ Prompted | ✅ Full | High |
| iOS Safari (installed) | ✅ Manual | ✅ Limited | Medium |
| iOS Safari (browser) | ❌ | ❌ | N/A |
| Desktop Chrome | ✅ Prompted | ✅ Full | High |
| Desktop Firefox | ❌ | ✅ Works | High |
| Desktop Safari | ✅ | ✅ Since Sonoma | Medium |

For v0.1 (dogfooding): acceptable. For v0.3 (public launch): wrap in Capacitor for native iOS/Android push via APNs/FCM.

---

## Voice Input — Architecture for Swappable Providers

### v0.1: Web Speech API (free, browser-built-in)

Uses `SpeechRecognition` API (Chrome uses Google's servers, quality is good). Safari and Firefox support is weaker. Since most mobile PWA users will be on Chrome (especially Android), this is acceptable.

**Critical UX decision already in spec:** transcript appears in input field for review, NOT auto-sent. This protects against bad transcription. User always sees and can edit what was recognized.

**Configuration in useVoice hook:**
```typescript
// Provider interface — swap implementations without changing components
interface VoiceProvider {
  startRecording(): void
  stopRecording(): void
  onTranscript: (text: string) => void
  onError: (error: string) => void
  isSupported: boolean
}
```

### v0.2 upgrade path: Whisper API or Deepgram

If Web Speech API feels unreliable during dogfooding, swap the provider:
- Record raw audio using MediaRecorder API (works everywhere)
- Send audio blob to Whisper API ($0.006/min) or Deepgram ($0.005/min)
- Return transcript to same `onTranscript` callback
- Components don't change — only the hook internals

This swap is a 1-2 hour change because the interface is the same.

---

## What This Spec Does NOT Cover

- Backend implementation (separate doc)
- System prompt / LLM logic (separate doc)
- Payment processing setup (Stripe integration — backend concern, frontend just opens a URL)
- Analytics or tracking (none in v0.1)
- Error logging service (none in v0.1)

---

## Implementation Priority

Build in this order:

1. **Scaffold:** Vite + React + TypeScript project, PWA manifest, basic CSS variables
2. **Chat layout:** ChatScreen with hardcoded mock messages (get the visual right)
3. **Input bar:** Text input with auto-expand, send button show/hide logic
4. **Message streaming:** Connect to a mock SSE endpoint, render tokens in real time
5. **Voice input:** Microphone button, Web Speech API, transcript in input field
6. **Auth:** Supabase Google OAuth (primary) + magic link (fallback)
7. **History:** Load previous messages on app open
8. **Push notifications:** Permission request, service worker registration
9. **Payment flow:** Rate limit message with Stripe checkout link
10. **Polish:** Animations, mobile edge cases, PWA install prompt

---

*Hand this entire document to Claude Code or Cursor. It contains everything needed to generate the complete frontend. Review the output, tweak the colors and feel, then deploy.*
