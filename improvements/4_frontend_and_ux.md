# 4. Frontend Architecture & UX: The Fluid Mind

## The Core Challenge: The Cognitive Load of Linear Chat
The current interface is a standard chat window. For a user with ADHD, this design has severe flaws:
1. **Working Memory Tax:** If the user asks "What do I need to do today?", the bot replies with a text block. Five messages later, that block has scrolled off-screen. The user has to either hold the list in their head or scroll up to find it.
2. **The "Wait" Anxiety:** While the bot streams its response, the user is blocked. If they remembered something else, they have to wait for the bot to finish before typing.
3. **The Categorization Paradox:** Because we want to avoid forcing the user to categorize things (e.g., clicking a "New Task" button), we need the UI to intelligently categorize things *for them*, visually separating actionable tasks from conversational reassurance.

## The Solution: A Split-Pane Local-First PWA

We need to evolve the frontend from a "Chatbot" to an "Intelligent Workspace" that operates instantly, even offline. We must design **mobile-first**, as an ADHD assistant is a "panic button" in the pocket, while ensuring desktop provides a powerful, expansive view.

### 1. The UX Redesign: Mobile vs. Desktop

The architecture relies on two core concepts: **The Stream** (unfiltered conversational input) and **The Plate** (the dynamic, spatial reality of the user's graph).

#### Mobile UX (The Primary Interface)
On a phone, screen real estate is at a premium. A permanent split-screen is impossible. Instead, we use a fluid, gesture-based layered approach.

*   **The Default View (The Stream):** When the app opens, it defaults to the chat interface. The keyboard immediately pops up. The user can instantly brain-dump.
*   **The Pull-Down Plate (The "Shelf"):** The Plate does not require a menu tap to access. Instead, the user **swipes down** from the top of the chat (like pulling down the Notification Center on iOS). 
    *   This reveals a clean, tactile shelf showing their active "Lenses":
        *   **Today's Timeline:** A horizontal scrolling list of events/deadlines for today.
        *   **Top of Mind:** 3-5 high-priority `OPEN` nodes displayed as swipeable cards.
        *   **Trackers:** Mini sparkline charts for active metrics (e.g., "Water drank today").
    *   **The interaction is transient:** They pull down to check their reality, release to let it spring back up, and continue typing in The Stream. This physically separates "doing/planning" from "dumping/processing."
*   **Interruptible Input:** The user must *always* be able to type or tap the microphone, even if the bot is "thinking" or streaming a response. Messages queue seamlessly.

#### Desktop UX (The Command Center)
On a laptop, the user is usually in a "working" or "review" mode. We utilize the horizontal space to completely offload working memory.

*   **The Split-Pane:**
    *   **Left Pane (1/3 width):** The Stream. It acts as the constant companion, processing text and voice.
    *   **Right Pane (2/3 width):** The Plate. This is permanently visible. It acts as a dynamic dashboard.
*   **The Magic Moment:** As the user types in the Stream ("remind me to call Mom tomorrow"), the background Archiver extracts the node. The moment it hits the local database, "Call Mom" magically slides into the "Tomorrow" section on The Plate on the right, without the bot needing to say a word. It feels like magic.

### 2. Aesthetics and Vibe: "Calm, Tactile, and Forgiving"
ADHD users are often overwhelmed by cluttered UIs, bright red "OVERDUE" badges, and aggressive gamification. Unspool must feel like a quiet, dimly lit room.

*   **Color Palette:** Deep, muted tones (charcoals, warm grays, soft sage greens). Avoid pure white backgrounds which cause eye strain.
*   **No "Failure" UI:** There are no bright red text warnings, no "Overdue by 5 days" badges. If a task slips past a deadline, it gracefully fades to a softer opacity, waiting to be rescheduled or gently dropped by the periodic graph evolution.
*   **Tactility:** Because the app doesn't rely on buttons for categorization, the elements that *do* exist must feel physical. Swiping away a task card in The Plate should have satisfying, springy physics (using Framer Motion or React Spring). It should feel like brushing a piece of paper off a desk.
*   **Typography:** Soft, highly legible sans-serifs (like Inter or San Francisco). Generous line height. The chat bubbles shouldn't look like iMessage; they should look like distinct thoughts floating on a canvas.

### 3. The Architectural Shift: Local-First (Zero Latency)
Currently, if the user goes offline, messages queue in `localStorage`, but the user cannot view past context or tasks.
*   **The Shift:** Adopt a **Local-First architecture**.
*   **The Tech Stack:** Use **PowerSync** or **ElectricSQL** in combination with an embedded browser database (like **SQLite via WASM** or **RxDB**).
*   **How it works:** 
    1.  A partition of the user's specific Graph Nodes, Edges, and the Event Stream is synced directly to the browser.
    2.  The UI frameworks (React) query the *local SQLite database*, not the server.
    3.  When the user opens the app on a subway with no cell service, the app loads in 0ms. They can pull down their Plate, read all their tasks, add new brain dumps, and close the app.
    4.  The local DB writes the events instantly, and seamlessly syncs them to Supabase the moment the phone regains connection.

### 4. State Management & SSE Stability
The current frontend relies on brittle string-splitting (`data.split('}\n\n{')`) to handle malformed Server-Sent Events (SSE). 
*   **Standardize the Stream:** The backend must be rewritten to strictly adhere to the SSE specification (yielding exact `data: <payload>\n\n` chunks).
*   **Decouple State from React:** The `ChatScreen.tsx` component is massively overloaded. We must introduce a global state manager (like **Zustand**). 
    *   The Zustand store handles the raw SSE connection, message queuing, and error retries entirely outside the React render cycle.
    *   React components simply subscribe to slices of this store (e.g., `const messages = useChatStore(state => state.messages)`), dramatically improving rendering performance and testing capability.