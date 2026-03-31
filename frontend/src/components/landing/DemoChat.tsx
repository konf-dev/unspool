import { useState, useEffect, useRef, useCallback } from 'react'
import { DemoMessage } from './DemoMessage'

interface DemoEntry {
  role: 'user' | 'assistant'
  content: string
}

const DEMO_SEQUENCES: DemoEntry[][] = [
  [
    { role: 'user', content: 'dentist, lease renewal friday, plant watering idea, text sarah, car registration expiring?' },
    { role: 'assistant', content: "got all five. lease renewal — friday. surfacing wednesday. dentist — next business hours. text sarah — quick one, now?" },
  ],
  [
    { role: 'user', content: 'what should I do next?' },
    { role: 'assistant', content: "call mom. it's quick and you'll feel good after." },
  ],
  [
    { role: 'user', content: "done. that was nice." },
    { role: 'assistant', content: 'checked that off. what else?' },
  ],
]

interface DemoChatProps {
  onSignIn: () => void
}

export function DemoChat({ onSignIn }: DemoChatProps) {
  const [messages, setMessages] = useState<DemoEntry[]>([])
  const [sequenceIndex, setSequenceIndex] = useState(0)
  const [isAutoPlaying, setIsAutoPlaying] = useState(true)
  const [input, setInput] = useState('')
  const [interactiveCount, setInteractiveCount] = useState(0)
  const [failCount, setFailCount] = useState(0)
  const [showSignInButtons, setShowSignInButtons] = useState(false)
  const [chatDisabled, setChatDisabled] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  const playSequence = useCallback((index: number) => {
    const seq = DEMO_SEQUENCES[index]
    if (!seq) {
      setIsAutoPlaying(false)
      setShowSignInButtons(true)
      return
    }

    // Show user message
    setMessages((prev) => [...prev, seq[0]!])
    timerRef.current = setTimeout(() => {
      // Show assistant message
      setMessages((prev) => [...prev, seq[1]!])
      timerRef.current = setTimeout(() => {
        setSequenceIndex(index + 1)
      }, 1500)
    }, 800)
  }, [])

  useEffect(() => {
    if (isAutoPlaying && sequenceIndex < DEMO_SEQUENCES.length) {
      // No delay for first sequence — start immediately
      const delay = sequenceIndex === 0 ? 0 : 1500
      timerRef.current = setTimeout(() => playSequence(sequenceIndex), delay)
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [isAutoPlaying, sequenceIndex, playSequence])

  useEffect(() => {
    const el = messagesContainerRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const handleFocus = () => {
    if (isAutoPlaying) {
      setIsAutoPlaying(false)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || chatDisabled) return

    const userMsg: DemoEntry = { role: 'user', content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    const newCount = interactiveCount + 1
    setInteractiveCount(newCount)

    if (newCount >= 3) {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: "that's a taste. sign up to keep going." },
        ])
        setChatDisabled(true)
        setShowSignInButtons(true)
      }, 600)
      return
    }

    try {
      const { sendDemoMessage } = await import('@/lib/demo-api')
      const allMessages = [...messages, userMsg]
      const response = await sendDemoMessage(allMessages)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: response.content },
      ])
      if (response.shouldPromptSignIn) {
        setShowSignInButtons(true)
      }
    } catch {
      const newFailCount = failCount + 1
      setFailCount(newFailCount)
      if (newFailCount >= 3) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: "demo's having trouble connecting. sign in to chat for real." },
        ])
        setChatDisabled(true)
        setShowSignInButtons(true)
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: "hmm, couldn't connect right now. try again or sign in to chat for real." },
        ])
      }
    }
  }

  return (
    <div className="w-full">
      <p className="text-on-surface-variant/50 text-[10px] tracking-[0.15em] uppercase mb-3 text-center">
        see how it works
      </p>
      <div className="bg-surface-container-high rounded-xl p-4 sm:p-6 shadow-[0_20px_40px_rgba(0,0,0,0.4)] text-left flex flex-col gap-6 ring-1 ring-outline-variant/10">
        <div ref={messagesContainerRef} className="space-y-3 sm:space-y-6 min-h-[200px] max-h-[200px] sm:max-h-[280px] overflow-y-auto no-scrollbar">
          {messages.map((msg, i) => (
            <div key={`${msg.role}-${i}`} className="animate-fade-in">
              <DemoMessage role={msg.role} content={msg.content} />
            </div>
          ))}
          {showSignInButtons && (
            <div className="flex gap-3 pt-2 animate-fade-in justify-center">
              <button onClick={onSignIn}
                className="px-4 py-1.5 rounded-full text-sm text-primary font-light tracking-wide ghost-border hover:bg-surface-container-high active:scale-[0.97] transition-all duration-300">
                sign up
              </button>
              <button onClick={onSignIn}
                className="px-4 py-1.5 rounded-full text-sm text-primary font-light tracking-wide ghost-border hover:bg-surface-container-high active:scale-[0.97] transition-all duration-300">
                log in
              </button>
            </div>
          )}
        </div>

        <div className="pt-4 border-t border-outline-variant/5">
          <div className={`bg-surface-container-low rounded-lg px-4 py-3 flex items-center justify-between${chatDisabled ? ' opacity-50' : ''}`}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={handleFocus}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleSend()
              }}
              disabled={chatDisabled}
              placeholder={chatDisabled ? 'sign up to continue' : "what's on your mind?"}
              className="bg-transparent text-on-surface placeholder:text-on-surface-variant/40 text-sm font-light w-full focus:outline-none disabled:cursor-not-allowed"
            />
            <button
              onClick={() => void handleSend()}
              disabled={chatDisabled}
              className="text-primary/60 hover:text-primary transition-colors ml-2 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Send demo message"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
