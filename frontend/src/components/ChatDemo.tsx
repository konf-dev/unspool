import { useState, useEffect, useRef, useCallback } from 'react'
import { sendDemoMessage } from '../lib/demo-api'
import type { ActionButton } from '../types'
import './ChatDemo.css'

interface DemoStep {
  role: 'user' | 'assistant'
  content: string
  actions?: ActionButton[]
  delay: number
}

const SEQUENCES: DemoStep[][] = [
  [
    {
      role: 'user',
      content:
        'I need to call the dentist, my lease renewal is due friday, I had a side project idea about plant watering, should text sarah back, and I think my car registration is expiring?',
      delay: 1500,
    },
    {
      role: 'assistant',
      content:
        "got all five.\nlease renewal — friday, I'll bring this up wednesday\ncall dentist — I'll remind you during business hours\ntext sarah — easy one, want to do it now?\ncar registration — I'll check when it's due\nplant watering project — saved the idea",
      delay: 2500,
    },
  ],
  [
    {
      role: 'user',
      content: 'what should I do',
      delay: 1500,
    },
    {
      role: 'assistant',
      content: "text sarah back — it's quick and you'll feel good after",
      actions: [
        { label: 'done', value: '__demo_done' },
        { label: 'skip', value: '__demo_skip' },
        { label: 'something else', value: '__demo_else' },
      ],
      delay: 2000,
    },
  ],
  [
    {
      role: 'assistant',
      content: "want to try it? sign in and I'll remember everything for you",
      actions: [
        { label: 'continue with Google', value: '__demo_google' },
        { label: 'use email', value: '__demo_email' },
      ],
      delay: 2000,
    },
  ],
]

// Sign-in action values that are interactive in demo mode
const SIGN_IN_ACTIONS = new Set(['__demo_google', '__demo_email'])

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  actions?: ActionButton[]
}

interface ChatDemoProps {
  onSignIn: () => void
}

function truncateForLabel(text: string, maxLen: number = 80): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

export function ChatDemo({ onSignIn }: ChatDemoProps) {
  const [mode, setMode] = useState<'demo' | 'chat'>('demo')
  const [currentSeq, setCurrentSeq] = useState(0)
  const [visibleSteps, setVisibleSteps] = useState(0)
  const [showTyping, setShowTyping] = useState(false)
  const [demoFading, setDemoFading] = useState(false)

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showSignIn, setShowSignIn] = useState(false)

  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const messageAreaRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const mountedRef = useRef(true)
  const prefersReducedMotion = useRef(window.matchMedia('(prefers-reduced-motion: reduce)').matches)

  // Track mounted state for async cleanup
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const clearTimeouts = useCallback(() => {
    timeoutsRef.current.forEach(clearTimeout)
    timeoutsRef.current = []
  }, [])

  // Cleanup all timeouts on unmount
  useEffect(() => clearTimeouts, [clearTimeouts])

  // Auto-play demo sequences
  useEffect(() => {
    if (mode !== 'demo') return

    if (prefersReducedMotion.current) {
      setCurrentSeq(0)
      const seq = SEQUENCES[0]
      if (seq) setVisibleSteps(seq.length)
      return
    }

    const seq = SEQUENCES[currentSeq]
    if (!seq) return

    clearTimeouts()
    setVisibleSteps(0)
    setShowTyping(false)
    setDemoFading(false)

    let totalDelay = 0

    seq.forEach((step, i) => {
      totalDelay += step.delay

      if (step.role === 'assistant') {
        const typingStart = totalDelay - 1200
        if (typingStart > 0) {
          const t = setTimeout(() => setShowTyping(true), typingStart)
          timeoutsRef.current.push(t)
        }
      }

      const t = setTimeout(() => {
        setShowTyping(false)
        setVisibleSteps(i + 1)
      }, totalDelay)
      timeoutsRef.current.push(t)
    })

    // Fade out before switching to next sequence
    const fadeDelay = totalDelay + 4000
    const tFade = setTimeout(() => setDemoFading(true), fadeDelay)
    timeoutsRef.current.push(tFade)

    const nextDelay = fadeDelay + 600
    const tNext = setTimeout(() => {
      setDemoFading(false)
      setCurrentSeq((prev) => (prev + 1) % SEQUENCES.length)
    }, nextDelay)
    timeoutsRef.current.push(tNext)

    return clearTimeouts
  }, [mode, currentSeq, clearTimeouts])

  // Scroll to bottom on new content
  useEffect(() => {
    const el = messageAreaRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [visibleSteps, chatMessages, showTyping, isLoading])

  const switchToChat = useCallback(() => {
    if (mode !== 'demo') return
    setDemoFading(true)
    clearTimeouts()
    const t = setTimeout(() => {
      if (!mountedRef.current) return
      setMode('chat')
      setDemoFading(false)
    }, 300)
    timeoutsRef.current.push(t)
  }, [mode, clearTimeouts])

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setInputValue(e.target.value)
      if (mode === 'demo') switchToChat()
    },
    [mode, switchToChat],
  )

  const handleInputFocus = useCallback(() => {
    if (mode === 'demo') switchToChat()
  }, [mode, switchToChat])

  const handleSend = useCallback(async () => {
    const text = inputValue.trim()
    if (!text || isLoading || showSignIn) return

    const userMsg: ChatMessage = { role: 'user', content: text }
    const newMessages = [...chatMessages, userMsg]
    setChatMessages(newMessages)
    setInputValue('')
    setIsLoading(true)

    try {
      const apiMessages = newMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }))
      const response = await sendDemoMessage(apiMessages)
      if (!mountedRef.current) return

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: response.content,
      }

      if (response.shouldPromptSignIn) {
        assistantMsg.actions = [
          { label: 'continue with Google', value: '__demo_google' },
          { label: 'use email', value: '__demo_email' },
        ]
        setShowSignIn(true)
      }

      setChatMessages((prev) => [...prev, assistantMsg])
    } catch {
      if (!mountedRef.current) return
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'hmm, something went wrong. try again?' },
      ])
    } finally {
      if (mountedRef.current) setIsLoading(false)
    }
  }, [inputValue, isLoading, showSignIn, chatMessages])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        void handleSend()
      }
    },
    [handleSend],
  )

  const handleAction = useCallback(
    (value: string) => {
      if (value === '__demo_google' || value === '__demo_email') {
        if (chatMessages.length > 0) {
          localStorage.setItem('unspool-demo-messages', JSON.stringify(chatMessages))
        }
        onSignIn()
      }
    },
    [chatMessages, onSignIn],
  )

  const renderActions = (actions: ActionButton[], interactive: boolean) => (
    <div className="demo-actions">
      {actions.map((action) => {
        const isClickable = interactive || SIGN_IN_ACTIONS.has(action.value)
        return (
          <button
            key={action.value}
            className={`demo-action-btn ${isClickable ? '' : 'decorative'}`}
            type="button"
            onClick={isClickable ? () => handleAction(action.value) : undefined}
            tabIndex={isClickable ? 0 : -1}
            aria-hidden={!isClickable}
          >
            {action.label}
          </button>
        )
      })}
    </div>
  )

  const renderMessage = (
    msg: { role: string; content: string; actions?: ActionButton[] },
    key: string,
    interactive: boolean,
  ) => {
    const label =
      msg.role === 'user'
        ? `You: ${truncateForLabel(msg.content)}`
        : `Unspool: ${truncateForLabel(msg.content)}`

    return (
      <div key={key} className={`demo-message-row ${msg.role}`} aria-label={label}>
        <div className={`demo-bubble ${msg.role}`}>
          {msg.content.split('\n').map((line, j) => (
            <p key={j}>{line}</p>
          ))}
        </div>
        {msg.actions && renderActions(msg.actions, interactive)}
      </div>
    )
  }

  const renderTypingIndicator = () => (
    <div className="demo-message-row assistant">
      <div className="demo-typing" role="status" aria-label="Thinking">
        <span className="demo-typing-dot" />
        <span className="demo-typing-dot" />
        <span className="demo-typing-dot" />
      </div>
    </div>
  )

  return (
    <div className="chat-demo-frame" aria-label="Chat demo">
      <div ref={messageAreaRef} className={`chat-demo-messages ${demoFading ? 'fading' : ''}`}>
        {mode === 'demo' &&
          SEQUENCES[currentSeq]
            ?.slice(0, visibleSteps)
            .map((step, i) => renderMessage(step, `demo-${currentSeq}-${i}`, false))}
        {mode === 'chat' && chatMessages.map((msg, i) => renderMessage(msg, `chat-${i}`, true))}
        {(showTyping || isLoading) && renderTypingIndicator()}
      </div>
      <div className="chat-demo-input">
        <input
          ref={inputRef}
          type="text"
          className="chat-demo-input-field"
          placeholder="what's on your mind?"
          value={inputValue}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          disabled={showSignIn}
          aria-label="Type a message to try the demo"
        />
        {inputValue.trim() && (
          <button
            className="chat-demo-send"
            type="button"
            onClick={() => void handleSend()}
            aria-label="Send message"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M5 12L12 5L19 12M12 5V19"
                stroke="#fff"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
