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
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const playSequence = useCallback((index: number) => {
    const seq = DEMO_SEQUENCES[index]
    if (!seq) {
      setIsAutoPlaying(false)
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

  const handleFocus = () => {
    if (isAutoPlaying) {
      setIsAutoPlaying(false)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }

  const handleSend = async () => {
    if (!input.trim()) return

    if (interactiveCount >= 5) {
      onSignIn()
      return
    }

    const userMsg: DemoEntry = { role: 'user', content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setInteractiveCount((c) => c + 1)

    try {
      const { sendDemoMessage } = await import('@/lib/demo-api')
      const allMessages = [...messages, userMsg]
      const response = await sendDemoMessage(allMessages)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: response.content },
      ])
      if (response.shouldPromptSignIn) {
        onSignIn()
      }
    } catch {
      const newFailCount = failCount + 1
      setFailCount(newFailCount)
      if (newFailCount >= 3) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: "demo's having trouble connecting. sign in to chat for real." },
        ])
        onSignIn()
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
      <div className="bg-surface-container-high rounded-xl p-6 shadow-[0_20px_40px_rgba(0,0,0,0.4)] text-left flex flex-col gap-6 ring-1 ring-outline-variant/10">
        <div className="space-y-6 min-h-[280px] max-h-64 overflow-y-auto no-scrollbar">
          {messages.map((msg, i) => (
            <div key={i} className="animate-fade-in">
              <DemoMessage role={msg.role} content={msg.content} />
            </div>
          ))}
        </div>

        <div className="pt-4" style={{ borderTop: '1px solid rgba(70, 73, 67, 0.05)' }}>
          <div className="bg-surface-container-low rounded-lg px-4 py-3 flex items-center justify-between">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={handleFocus}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleSend()
              }}
              placeholder="what's on your mind?"
              className="bg-transparent text-on-surface placeholder:text-on-surface-variant/40 text-sm font-light w-full focus:outline-none"
            />
            <button
              onClick={() => void handleSend()}
              className="text-primary/60 hover:text-primary transition-colors ml-2"
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
