# Product Lifecycle — What Unspool Should Do at Every Stage

What the ideal product looks like from the customer's perspective. Not what's built, not what's in progress — what should exist. Organized by where the user is in their journey.

---

## Who We're Building For

### Primary: People with ADHD who have given up on productivity tools

They've tried Notion, Todoist, Apple Reminders, physical planners, bullet journals. Each one lasted 3 days to 2 weeks. The pattern is always the same: exciting setup → honeymoon → the system gets heavier → abandonment → guilt. They don't need another tool that asks them to be organized. They need something that handles the organization they can't do.

**Profile:** 20s-30s, students or early-career professionals. Diagnosed or self-aware ADHD. Smartphone-first. Willing to pay $8/month if something actually works. They've spent more on planners they abandoned.

**What they say:**
- "I forget things constantly and lists just become another thing I ignore"
- "I know what I need to do, I just can't make myself start"
- "Every productivity app assumes I can be productive"
- "I set reminders and then I snooze them until they stop"

### Secondary: Overwhelmed people who don't identify as ADHD

They might not have a diagnosis. They're just... drowning. Too many things in too many places. Work Slack, personal notes app, random texts to themselves, sticky notes. Their "system" is chaos and they know it, but they don't have the bandwidth to build a better one.

**Profile:** Any age. Often juggling multiple life areas (work + school, work + family, freelancing + side project). Uses their phone for everything. Price-sensitive but not broke — $8/month is fine if the value is clear.

**What they say:**
- "I have stuff everywhere and I can't find anything"
- "I just need something to tell me what to do next"
- "I don't have time to organize my life, that's the whole problem"

### Who we're NOT building for

- **Productivity enthusiasts** who enjoy building Notion databases and tweaking systems. They already have what they want
- **Teams or managers** who need project management. We don't do collaboration, boards, or assignments
- **People who want a general AI assistant.** We don't answer trivia, write emails, or generate content. One job: manage the chaos in your head
- **People who want control and customization.** No settings page, no themes, no notification preferences to tune. If that's frustrating, this isn't the right tool

---

## Stage 1: Discovery

**User is thinking:** "What is this? Is it another productivity app I'll abandon?"

### What should happen

**Finding us**
- Search "ADHD task manager" / "ADHD productivity" / "brain dump app" → we appear
- App Store / Play Store listing (eventually) with clear ADHD-first positioning
- Social proof from ADHD communities (Reddit, TikTok, Twitter) — real users, not influencer marketing

**First impression (landing page / store listing)**
- Immediately clear this is NOT another todo list. The anti-productivity-app positioning must hit in the first 3 seconds
- No feature comparison table. No "vs Notion" framing. That's speaking the wrong language
- Show what the chat looks like. One screenshot of a brain dump → AI response. That's the pitch
- The "why this is different" must land emotionally: "You don't organize anything. You just talk."
- Price visible upfront: free (10 msgs/day), $8/month unlimited. No "contact sales," no hidden tiers
- One CTA: try it. Not "learn more," not "watch a demo"

### Cases to handle

- User lands from a Google search for "ADHD planner" → needs to understand in 5 seconds this isn't a planner
- User lands from a friend's recommendation → needs to trust it enough to try
- User lands at 2am in an ADHD hyperfocus research spiral → don't lose them with a wall of text
- User with app fatigue ("I've tried everything") → the landing page itself must not feel like every other SaaS landing page
- User on mobile → install path must be obvious (PWA "add to home screen" or native app)
- User who doesn't know they have ADHD but relates to "I forget everything and lists don't work" → inclusive language, not clinical

---

## Stage 2: First 5 Minutes

**User is thinking:** "How does this work? Do I need to set anything up?"

### What should happen

**Sign up**
- One tap: "Continue with Google." That's it. Account created, calendar connected, done
- Fallback: email magic link for users who don't want Google OAuth
- No username to choose, no profile to fill, no preferences to set, no onboarding wizard, no "choose your goals" screen
- Time from "I want to try this" to "I'm using it": under 30 seconds

**First message**
- The AI speaks first: one casual line inviting a brain dump. Not a tutorial, not a feature tour
- User types anything — messy, half-formed, multiple things in one message — and it just works
- AI responds with a short acknowledgment showing it understood. No follow-up questions unless something is genuinely ambiguous (like a deadline mentioned without a date)
- The moment should feel like texting a friend, not onboarding into software

**Building understanding**
- Within the first 2-3 messages, the user should intuitively get: "I dump stuff, it remembers, it'll remind me"
- No need to explain features. The product teaches itself through use
- If user asks "what can you do?" — answer in one short paragraph, conversationally. Not a feature list

### Cases to handle

- User types "hi" → warm response, invite to dump. Don't over-explain
- User dumps 10 things in one message → handle all of them, acknowledge each briefly
- User types a single task with a deadline → capture it, confirm the deadline, done
- User types something emotional ("I'm so stressed") → respond with empathy, not task capture
- User types in a language other than English → respond in that language automatically
- User is skeptical ("is this just ChatGPT?") → honest answer about what it does differently
- User tries to test it ("remember the number 42") → just remember it, don't be defensive
- User signed up via magic link (no Google) → calendar not connected. Don't nag about it now. Offer to connect later when calendar context would have been useful
- User on a very slow connection → the first response must still feel fast (streaming helps)
- User accidentally closes the app and comes back → conversation is still there, no progress lost

---

## Stage 3: First Week

**User is thinking:** "Is this worth keeping? Will I actually use this?"

### What should happen

**The habit forms (or doesn't)**
- User opens the app 2-3 times → the AI has context from previous conversations. It remembers what was dumped. This is the "oh wow" moment
- Proactive messages on app open: "hey, rent's due in 2 days" or "you mentioned wanting to call your mom last week" — delivered casually, not as alerts
- First "what should I do?" → AI picks ONE thing. Not a list. The right thing, based on urgency and energy
- First "done" → satisfying acknowledgment. If momentum is building, note it: "that's three today"
- First deadline reminder (push notification) → one notification, when it actually matters. User thinks "ok, this app respects my attention"

**Trust building**
- AI correctly infers soft vs hard deadlines from natural language
- AI doesn't nag about things the user deprioritized
- When user comes back after a day of silence — no guilt, no "you missed..." Just picks up where they left off
- When user says "bad day" or "overwhelmed" → everything soft gets pushed. No productivity guilt

**PWA install prompt**
- After a few conversations, a gentle in-chat suggestion: "tip: add me to your home screen for the best experience." Not a modal, not a banner. Just a message
- On Android: native install prompt if available
- On iOS: brief instructions for "add to home screen"

### Cases to handle

- User dumps things across 3 separate sessions → AI connects them all into one coherent picture
- User mentions a deadline in casual conversation ("oh yeah that's due friday") → captured even though it wasn't explicitly a task
- User asks "what did I tell you about the thesis?" → AI recalls across sessions accurately
- User goes quiet for 3 days → no push notifications unless hard deadline. When they return, gentle "welcome back" with only what matters
- User dumps duplicates ("need to do laundry" again when laundry is already tracked) → handled gracefully, not "you already told me this"
- User corrects the AI ("no, the meeting is Wednesday not Thursday") → immediate update, no friction
- User says "actually never mind about the dentist" → item removed, confirmed
- User's first push notification → must be genuinely useful (hard deadline) to build trust in the notification system
- User on free tier hits the 10 message limit → the upgrade prompt is one message, one tap, no pressure. Not a paywall modal

---

## Stage 4: Daily Use

**User is thinking:** "Let me dump / do / done. This is how I stay on top of things."

### What should happen

**The core loop**
- Brain dump → AI extracts and acknowledges. Multiple items in one messy message, all handled
- "What should I do?" → ONE item. Calibrated to urgency + energy. With action buttons: [done] [skip] [something else]
- "Done" → acknowledged, momentum tracked. If on a roll: "that's 4 today" with next suggestion
- "Can't right now" / "skip" → rescheduled, no guilt. Next option offered
- "What's coming up?" → only things with real consequences in the next 48h. Calendar events included

**Action buttons**
- When the AI suggests a task, tappable buttons appear: [done] [skip] [something else]
- After marking done: [yes give me another] [I'm good for now]
- On emotional messages: NO buttons. Just text. Buttons would be tone-deaf
- Buttons reduce friction — the user shouldn't have to type "done" every time

**Calendar awareness**
- "You have a meeting with Chen at 2pm" surfaced proactively when relevant
- "Your week looks packed — maybe knock out the easy stuff today" based on calendar density
- Conflict detection: "you said lunch with Erik Wednesday but you have a seminar at 12:30"
- Honest about limitations: "I can read your calendar but can't add to it"

**Recurring things**
- Rent, meds, groceries — the AI learns these are recurring without being told
- "Paid rent" → "see you next month for the same reminder"
- Medication reminders: "meds?" — one word, every morning, if the user asked for it
- No streak tracking, no "you've taken meds 5 days in a row!" gamification

**Voice input**
- Tap mic, talk, transcript appears in input for review. Not auto-sent — ADHD users ramble and need to edit
- Works for brain dumps while walking, driving, lying in bed
- Silence detection stops recording after 3 seconds
- If speech recognition fails, graceful fallback to typing

**Fuzzy deadlines**
- "soon" → ~2 days. "next week" → 5-7 days. "at some point" → parked
- "At your earliest convenience" → AI applies social knowledge: "that usually means within a week"
- Easter, holidays, known dates → AI fills in without asking
- Flight booking → AI knows prices spike 3-4 weeks out and factors that in

### Cases to handle

- User dumps 3 things while walking → voice input handles it, AI extracts all 3
- User says "finished the email" but has 2 emails tracked → AI asks "which one?" with buttons: [extension email] [PhD program]
- User is in flow state (3 things done in a row) → AI notices momentum, suggests something slightly bigger. "You've got momentum — maybe tackle the lit review?"
- User marks something done that they didn't tell the AI about → "nice. I didn't have that on my radar — was it something new or something I missed?"
- User dumps something at 3am → no judgment about the time. Just captures it. Maybe "now go to sleep" if it's clearly late
- User mentions an event without explicitly asking to track it ("told Erik I'd help him move Saturday") → captured, Saturday kept clear of nudges
- User says "actually that deadline moved to next week" → updated immediately, all related nudges adjusted
- User types in a different language mid-conversation → AI switches language without comment
- User on a bad connection → messages queued and sent when back online. No lost data

---

## Stage 5: "Does It Know Me?"

**User is thinking:** "Is this thing actually learning? Does it get me?"

### What should happen

**Pattern recognition**
- "I noticed you're more productive early in the week — want me to save some easy wins for Wednesday when things usually slow down?"
- "The weeks where you mentioned going for walks, you completed about 40% more tasks. Not saying you should — just noticed"
- "You tend to dump a lot on Sunday evenings — that's usually your planning mode"
- These insights surface naturally in conversation, not as reports or dashboards

**Emotional intelligence**
- User says "I'm not getting anywhere" → AI counters with actual data: "You've done 47 things this month. Your brain is lying to you"
- User is frustrated with a specific task → AI offers to break it down into 5-15 minute chunks (not a generic "try pomodoro!")
- User is venting, not asking for help → AI listens, validates, doesn't try to solve. But silently notes relevant info for later
- User's tone shifts (shorter messages, more negative) → AI adjusts: softer, less pushy, fewer suggestions

**Personalization that compounds**
- AI learns energy patterns: this user doesn't do deep work on Sundays
- AI learns communication preferences: this user likes direct suggestions, not open-ended questions
- AI remembers relationships: "your mom" "your supervisor Chen" "your friend Erik" — no need to re-explain context
- AI connects ideas across weeks: "you mentioned attention mechanisms 3 weeks ago — could that be relevant to the fleet optimization problem?"
- When user gives feedback ("that suggestion was bad, I'd never do lit review on a Sunday") → AI actually adjusts, permanently

**Progress visibility (only when asked)**
- "How's the thesis going?" → AI assembles a status picture from weeks of conversations. Chapter 1 done, chapter 2 in progress, chapter 3 needs rework...
- "What did I do this week?" → summary useful for standups, weekly reports, self-reflection
- "Am I making progress?" → honest answer based on data, calibrated to counter ADHD catastrophizing
- This is never shown unprompted. No weekly review, no progress report, no "here's your month"

### Cases to handle

- User asks about a pattern the AI hasn't detected yet → honest: "I don't have enough data yet, but I'll keep an eye on it"
- AI's pattern insight is wrong → user corrects it, AI adjusts without being defensive
- User asks "what do you know about me?" → transparent summary of learned preferences, patterns, relationships. No hidden knowledge
- User mentions something from months ago that they expect the AI to remember → it does. This is the magic moment
- User's life circumstances change (new job, breakup, moved cities) → AI adapts to new context without clinging to old patterns
- Two ideas from different months are related → AI connects them proactively: "this reminds me of something you said in January"

---

## Stage 6: Power User (30+ Days)

**User is thinking:** "This is how I run my life. Find that thing from 3 weeks ago."

### What should happen

**Deep memory search**
- "Did I ever think about something related to machine learning for my thesis?" → AI surfaces 3 related entries from different weeks with context
- "When did I last call my mom?" → exact date, from conversation history
- "What was that paper I found at 11pm last Tuesday?" → AI remembers the context even if the user was vague

**Long-term project support**
- Thesis, job applications, moving house — the AI tracks multi-week projects from conversational mentions alone
- "Work backwards from June 12 and set up nudge points" → AI creates a timeline with milestone reminders
- Progress on big projects is assembled from dozens of small "done" moments across weeks

**Task decomposition**
- "Write chapter 3" is too big → AI breaks it into: write the section header (5 min), list key papers (10 min), draft one paragraph (15 min)
- Decomposition is specific to what the user has mentioned, not generic advice
- "Which one feels least scary?" — framed for ADHD brains, not neurotypical productivity advice

**Idea web**
- Ideas captured over months form connections. The AI proactively surfaces relevant past ideas when the user is working on something related
- "You had 3 ideas about fleet optimization over the last 2 months — want me to pull them together?"
- This is the "second brain" that Notion promises but requires manual maintenance

**Social and relationship tracking**
- "You mentioned wanting to call your mom about 2 weeks ago. Has that happened?" — gentle, not naggy
- Birthday reminders with shipping time factored in
- "Erik's birthday is in 10 days, you mentioned ordering online — I'll nudge you in 3-4 days so shipping works out"
- Tracks social commitments: "you told Erik you'd help move Saturday — I'll keep that day clear"

**Administrative life support**
- Tax deadlines with country-specific knowledge
- Recurring bills and subscriptions tracked from mentions
- "You said you wanted to cancel Crunchyroll — these things are always harder to cancel than sign up for. Want me to nudge you when you have 5 minutes?"
- Lease renewals, insurance, appointments — all tracked from conversation

### Cases to handle

- User searches for something vague ("that thing about scheduling") → AI uses semantic search, not just keyword matching
- User has 200+ items over 3 months → performance stays fast, relevance stays sharp
- User's priorities shift significantly (thesis done, starting a job) → AI adapts its entire mental model
- User references something they told the AI months ago → it's still there
- User asks the AI to plan something complex (PhD application with 5 sub-tasks and dependencies) → AI creates a timeline and tracks it over weeks
- User travels to a different timezone → deadline calculations adjust automatically
- User mentions the same person in different contexts over months → AI maintains a coherent understanding of relationships

---

## Stage 7: Something Went Wrong

**User is thinking:** "It missed my deadline / it got it wrong / it's being annoying."

### What should happen

**Missed deadline**
- If a hard deadline notification didn't fire or the user missed it → AI acknowledges without making it worse: "the rent deadline passed yesterday. want me to set a reminder for the late payment, or is it handled?"
- No "you should have done this yesterday!" — just practical next steps
- If the system was at fault (notification didn't send) → honest about it

**Bad suggestion**
- User says "that was a bad suggestion" → AI asks why (or infers from context) and adjusts
- "I'd never do the lit review on a Sunday" → permanently learned, not just this once
- "Stop suggesting I exercise" → respected immediately, no passive-aggressive "but it helped before..."

**Wrong interpretation**
- AI misunderstood what the user meant → easy to correct: "no I meant the OTHER email"
- AI inferred wrong deadline → corrected in one message, all related nudges updated
- AI captured something that wasn't a task (user was just venting) → "actually forget about that, I was just ranting" → removed

**AI is being annoying**
- Too many proactive messages → user says "chill" or "stop nudging me" → AI backs off significantly
- Tone feels wrong → user gives feedback → AI adjusts personality (more direct, less chatty, etc.)
- AI is too cheerful when user is struggling → mirrors energy better going forward

**Technical failure**
- App is slow or unresponsive → clear indication something is wrong, not silent failure
- Message didn't send → visible retry option, message not lost
- AI gives a nonsensical response → user can ignore it and move on, or flag it

**Data concerns**
- "What data do you have on me?" → transparent, complete answer
- "Delete everything about the thesis" → selective deletion works
- "Delete my account" → everything gone, confirmed, no "are you sure?" dark pattern (one confirmation is fine)

### Cases to handle

- User is frustrated WITH the app → don't respond with the same cheerful tone. Acknowledge the frustration
- User hits the same bug twice → don't give the same "sorry about that" — escalate: "this keeps happening, I'm sorry. here's what I know..."
- User's trust is broken (missed an important deadline due to app) → recovery is about actions not apologies. "Here's what I'll do differently"
- Push notification fired during quiet hours → user is annoyed → AI apologizes, adjusts quiet hours
- User wants to know why the AI suggested something → explain the reasoning: "I picked this because it's due tomorrow and it's a quick one"

---

## Stage 8: Leaving, Pausing, or Getting Help

**User is thinking:** "I want out / I need help / I'm taking a break / I want to come back."

### What should happen

**Taking a break**
- User stops using the app for weeks → nothing happens. No re-engagement emails, no "we miss you" push notifications. Silence
- When they come back, whenever that is → "hey, welcome back" with only what's urgent. No guilt about the gap
- Items with soft deadlines may have faded (urgency decayed). That's fine. If they mattered, the user will mention them again

**Canceling subscription**
- "Cancel my subscription" → handled in chat. One confirmation. Done
- User keeps access until end of billing period
- Drops to free tier (10 msgs/day), not locked out. All data stays
- No "but you'll lose access to..." manipulation. No exit survey. No "we'll miss you"

**Deleting account**
- "Delete my account" → one confirmation → everything gone. Actually deleted, not "deactivated"
- Clear about what's deleted: messages, items, profile, push subscriptions. Everything
- No 30-day "just in case" retention (or if required by law, transparent about it)

**Coming back after deletion**
- User signs up again → fresh start. No ghost data, no "welcome back"
- Previous data is genuinely gone

**Getting help / reporting problems**
- "Something is broken" or "I need help" → clear path to reach a human (email, form, whatever exists)
- Not another chatbot. Not a FAQ page. A way to talk to the person building this
- Bug reports should be easy: "what happened?" in chat, AI helps capture the context

**Export**
- "Can I get my data?" → user can export their items, messages, and any extracted data
- Standard format (JSON, CSV). Not locked in

### Cases to handle

- User returns after 6 months → app still works, data still there (if not deleted), AI picks up from last known state
- User wants to try the app again after deleting → clean fresh start, no awkwardness
- User is leaving because the product doesn't work for them → learn from it. Make feedback easy, not guilt-inducing
- User is leaving because they're "cured" (their system is working, they don't need help) → that's a success, not a churn event
- User hit the free tier limit and can't afford $8/month → respect that. The free tier should still be genuinely useful at 10 msgs/day
- User wants to recommend the app to a friend → easy sharing (link, not invite code)
- User has accessibility needs (screen reader, reduced motion, larger text) → the app works for them without special settings

---

## Cross-Cutting Concerns

These apply to every stage, not just one.

### Privacy and trust
- The user is giving this app their innermost thoughts, anxieties, deadlines, and relationships. That's sacred
- End-to-end data handling must be transparent and trustworthy
- No selling data. No training on user data. No analytics that feel creepy
- GDPR-compliant from day one (the target audience includes Europeans)

### Accessibility
- Screen reader support for the chat interface
- Keyboard navigation for everything
- Reduced motion for users who need it
- Sufficient color contrast
- Works on low-end phones, slow connections
- Minimum 16px input text (prevents iOS zoom)

### Internationalization
- Auto-detect language from user's first message
- Respond in the same language
- Handle mixed-language conversations (user switches between English and Swedish)
- Date formats, currency references, cultural norms (tax deadlines, holidays) adapt to user's context

### Offline resilience
- App opens even without connection (cached shell)
- Messages queue and send when back online
- Clear "offline" indicator, not a broken-looking screen
- No data loss from connectivity issues

### Notification philosophy
- Max 1 push notification per day. Period
- Only for hard deadlines within 24 hours
- Everything else waits for the user to open the app
- Days of silence = the product working correctly
- User should develop trust: "when this app pings me, it actually matters"

---

*This document describes what the product should do. It does not describe what is built, what's in progress, or implementation details. Use it to evaluate gaps, prioritize work, and make product decisions.*
