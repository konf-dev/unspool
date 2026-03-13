import { useState, useCallback, useRef, useEffect } from 'react'
import type { Message, ActionButton } from '../types'
import { sendMessage } from '../lib/api'
import { useOffline } from '../hooks/useOffline'
import { usePush } from '../hooks/usePush'
import { useCatEasterEgg } from '../hooks/useCatEasterEgg'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { OfflineBanner } from './OfflineBanner'
import { CatEasterEgg } from './CatEasterEgg'
import './ChatScreen.css'

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback for non-secure contexts (e.g. HTTP on mobile)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function getSessionId(): string {
  const KEY = 'unspool-session-id'
  const existing = localStorage.getItem(KEY)
  if (existing) return existing

  const id = generateId()
  localStorage.setItem(KEY, id)
  return id
}

interface ChatScreenProps {
  initialMessages: Message[]
  token: string
  userId: string
  onSignOut: () => Promise<void>
}

export function ChatScreen({ initialMessages, token, userId: _userId, onSignOut }: ChatScreenProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [streamingContent, setStreamingContent] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [lastAssistantContent, setLastAssistantContent] = useState<string | null>(null)
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const pendingActionsRef = useRef<ActionButton[] | null>(null)
  const firstTokenReceivedRef = useRef(false)
  const sessionIdRef = useRef(getSessionId())

  const { isOnline } = useOffline()
  const messageCount = messages.length

  usePush(token, messageCount)

  const { showCat, variant, onCatDone } = useCatEasterEgg(
    messageCount,
    isStreaming,
    isThinking,
    lastAssistantContent,
  )

  useEffect(() => {
    if (isOnline) {
      document.body.classList.add('in-chat')
    }
    return () => {
      document.body.classList.remove('in-chat')
    }
  }, [isOnline])

  const flushQueue = useCallback(
    (queue: string[]) => {
      if (queue.length === 0) return

      const first = queue[0] as string
      const rest = queue.slice(1)
      setQueuedMessages(rest)

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: first,
        createdAt: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsThinking(true)
      setIsStreaming(true)
      setStreamingContent('')
      pendingActionsRef.current = null
      firstTokenReceivedRef.current = false

      let accumulated = ''

      const controller = sendMessage(
        first,
        sessionIdRef.current,
        token,
        (t) => {
          if (!firstTokenReceivedRef.current) {
            firstTokenReceivedRef.current = true
            setIsThinking(false)
          }
          accumulated += t
          setStreamingContent(accumulated)
        },
        (actions) => {
          pendingActionsRef.current = actions
        },
        () => {
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: accumulated,
            createdAt: new Date().toISOString(),
            actions: pendingActionsRef.current ?? undefined,
          }

          setMessages((prev) => [...prev, assistantMessage])
          setLastAssistantContent(accumulated)
          setStreamingContent(null)
          setIsStreaming(false)
          setIsThinking(false)
          abortRef.current = null
          pendingActionsRef.current = null
          firstTokenReceivedRef.current = false

          if (rest.length > 0) {
            setTimeout(() => flushQueue(rest), 500)
          }
        },
        () => {
          setIsStreaming(false)
          setIsThinking(false)
          setStreamingContent(null)
          abortRef.current = null
        },
      )

      abortRef.current = controller
    },
    [token],
  )

  useEffect(() => {
    if (isOnline && queuedMessages.length > 0 && !isStreaming && !isThinking) {
      flushQueue(queuedMessages)
    }
  }, [isOnline, queuedMessages, isStreaming, isThinking, flushQueue])

  const handleSend = useCallback(
    (text: string) => {
      if (isStreaming || isThinking) return

      if (!isOnline) {
        const userMessage: Message = {
          id: `user-${Date.now()}`,
          role: 'user',
          content: text,
          createdAt: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, userMessage])
        setQueuedMessages((prev) => [...prev, text])
        return
      }

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        createdAt: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsThinking(true)
      setIsStreaming(true)
      setStreamingContent('')
      pendingActionsRef.current = null
      firstTokenReceivedRef.current = false

      let accumulated = ''

      const controller = sendMessage(
        text,
        sessionIdRef.current,
        token,
        (t) => {
          if (!firstTokenReceivedRef.current) {
            firstTokenReceivedRef.current = true
            setIsThinking(false)
          }
          accumulated += t
          setStreamingContent(accumulated)
        },
        (actions) => {
          pendingActionsRef.current = actions
        },
        () => {
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: accumulated,
            createdAt: new Date().toISOString(),
            actions: pendingActionsRef.current ?? undefined,
          }

          setMessages((prev) => [...prev, assistantMessage])
          setLastAssistantContent(accumulated)
          setStreamingContent(null)
          setIsStreaming(false)
          setIsThinking(false)
          abortRef.current = null
          pendingActionsRef.current = null
          firstTokenReceivedRef.current = false
        },
        () => {
          setIsStreaming(false)
          setIsThinking(false)
          setStreamingContent(null)
          abortRef.current = null
        },
      )

      abortRef.current = controller
    },
    [isStreaming, isThinking, isOnline, token],
  )

  const handleAction = useCallback(
    (value: string) => {
      handleSend(value)
    },
    [handleSend],
  )

  const handleSignOut = useCallback(() => {
    void onSignOut()
  }, [onSignOut])

  return (
    <div className="chat-screen">
      <div className="stars">
        <div className="stars-small" />
        <div className="stars-medium" />
        <div className="stars-large" />
      </div>
      <button
        className="sign-out-btn"
        type="button"
        onClick={handleSignOut}
        aria-label="Sign out"
      >
        sign out
      </button>
      <OfflineBanner visible={!isOnline} />
      <div className="chat-container">
        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          isThinking={isThinking}
          onAction={handleAction}
        />
        <InputBar onSend={handleSend} disabled={isStreaming || isThinking} />
      </div>
      {showCat && <CatEasterEgg variant={variant} onDone={onCatDone} />}
    </div>
  )
}
