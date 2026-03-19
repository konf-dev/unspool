import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import type { Message, ActionButton } from '../types'
import { sendMessage } from '../lib/api'
import { parseInlineActions } from '../lib/parseActions'
import { useOffline } from '../hooks/useOffline'
import { usePush } from '../hooks/usePush'
import { useCatEasterEgg } from '../hooks/useCatEasterEgg'
import { usePWAInstall } from '../hooks/usePWAInstall'
import { useUIMode } from '../contexts/UIMode'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { OfflineBanner } from './OfflineBanner'
import { CatEasterEgg } from './CatEasterEgg'
import './ChatScreen.css'

const TOOL_LABELS: Record<string, string> = {
  save_items: 'saving...',
  mark_done: 'marking done...',
  pick_next: 'picking your next move...',
  search: 'searching...',
  get_upcoming: 'checking your schedule...',
  get_progress: 'checking progress...',
  update_item: 'updating...',
  remove_item: 'removing...',
  save_preference: 'noting that...',
  decompose_task: 'breaking it down...',
  remember: 'remembering...',
  save_event: 'saving event...',
  log_entry: 'logging...',
  get_tracker_summary: 'checking tracker...',
  save_note: 'saving note...',
  schedule_action: 'scheduling...',
  manage_collection: 'managing list...',
}

const QUEUE_KEY = 'unspool-queue'

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
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

function loadQueue(): string[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed as string[]
  } catch {
    // Corrupted data
  }
  return []
}

interface ChatScreenProps {
  initialMessages: Message[]
  token: string
  userId: string
  onSignOut: () => Promise<void>
}

export function ChatScreen({
  initialMessages,
  token,
  userId: _userId,
  onSignOut,
}: ChatScreenProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [streamingContent, setStreamingContent] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [lastAssistantContent, setLastAssistantContent] = useState<string | null>(null)
  const [toolStatus, setToolStatus] = useState<string | null>(null)
  const { uiMode, setUIMode } = useUIMode()
  const [queuedMessages, setQueuedMessages] = useState<string[]>(loadQueue)
  const abortRef = useRef<AbortController | null>(null)
  const pendingActionsRef = useRef<ActionButton[] | null>(null)
  const firstTokenReceivedRef = useRef(false)
  const userAbortedRef = useRef(false)
  const accumulatedRef = useRef('')
  const rafRef = useRef<number | null>(null)
  const sessionIdRef = useRef(getSessionId())
  const pwaPromptShownRef = useRef(false)

  const { isOnline } = useOffline()
  const messageCount = messages.length

  usePush(token, messageCount)

  const { showCat, variant, onCatDone } = useCatEasterEgg(
    messageCount,
    isStreaming,
    isThinking,
    lastAssistantContent,
  )

  const {
    showPrompt: showPWA,
    isIOS,
    triggerInstall,
    dismiss: dismissPWA,
  } = usePWAInstall(messageCount)

  // Persist queue to localStorage
  useEffect(() => {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queuedMessages))
  }, [queuedMessages])

  // Deduplicate queue against fetched messages on mount
  useEffect(() => {
    if (initialMessages.length > 0 && queuedMessages.length > 0) {
      const existingContent = new Set(
        initialMessages.filter((m) => m.role === 'user').map((m) => m.content),
      )
      setQueuedMessages((prev) => prev.filter((text) => !existingContent.has(text)))
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // PWA install prompt as system message
  useEffect(() => {
    if (showPWA && !pwaPromptShownRef.current) {
      pwaPromptShownRef.current = true
      const pwaMessage: Message = {
        id: `pwa-${Date.now()}`,
        role: 'assistant',
        content: 'add unspool to your home screen for the full experience',
        createdAt: new Date().toISOString(),
        actions: isIOS
          ? [{ label: 'show me how', value: '__pwa_ios' }]
          : [
              { label: 'install', value: '__pwa_install' },
              { label: 'not now', value: '__pwa_dismiss' },
            ],
        metadata: { isSystem: true },
      }
      setMessages((prev) => [...prev, pwaMessage])
    }
  }, [showPWA, isIOS])

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

      setIsThinking(true)
      setIsStreaming(true)
      setStreamingContent('')
      pendingActionsRef.current = null
      firstTokenReceivedRef.current = false
      userAbortedRef.current = false
      accumulatedRef.current = ''

      const controller = sendMessage(
        first,
        sessionIdRef.current,
        token,
        (t) => {
          if (!firstTokenReceivedRef.current) {
            firstTokenReceivedRef.current = true
            setIsThinking(false)
          }
          accumulatedRef.current += t
          if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
              setStreamingContent(accumulatedRef.current)
              rafRef.current = null
            })
          }
        },
        (actions) => {
          pendingActionsRef.current = actions
        },
        (tool, status) => {
          setToolStatus(status === 'running' ? (TOOL_LABELS[tool] ?? `${tool}...`) : null)
        },
        () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          const finalContent = accumulatedRef.current
          const { cleanContent, actions: inlineActions } = parseInlineActions(finalContent)
          const allActions = [...(pendingActionsRef.current ?? []), ...inlineActions]

          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: cleanContent,
            createdAt: new Date().toISOString(),
            actions: allActions.length > 0 ? allActions : undefined,
          }

          setMessages((prev) => [...prev, assistantMessage])
          setLastAssistantContent(cleanContent)
          setStreamingContent(null)
          setIsStreaming(false)
          setIsThinking(false)
          setToolStatus(null)
          abortRef.current = null
          pendingActionsRef.current = null
          firstTokenReceivedRef.current = false

          if (rest.length > 0) {
            setTimeout(() => flushQueue(rest), 500)
          }
        },
        () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          if (userAbortedRef.current) {
            userAbortedRef.current = false
            return
          }
          setIsStreaming(false)
          setIsThinking(false)
          setStreamingContent(null)
          setToolStatus(null)
          abortRef.current = null

          const errorMessage: Message = {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: "couldn't reach the server — try again?",
            createdAt: new Date().toISOString(),
            actions: [{ label: 'retry', value: first }],
            metadata: { isError: true },
          }
          setMessages((prev) => [...prev, errorMessage])
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

  const handleStop = useCallback(() => {
    userAbortedRef.current = true
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setIsStreaming(false)
    setIsThinking(false)
    setStreamingContent(null)
    setToolStatus(null)
  }, [])

  const handleSend = useCallback(
    (text: string) => {
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

      if (isStreaming || isThinking) {
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
      userAbortedRef.current = false
      accumulatedRef.current = ''

      const controller = sendMessage(
        text,
        sessionIdRef.current,
        token,
        (t) => {
          if (!firstTokenReceivedRef.current) {
            firstTokenReceivedRef.current = true
            setIsThinking(false)
          }
          accumulatedRef.current += t
          if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
              setStreamingContent(accumulatedRef.current)
              rafRef.current = null
            })
          }
        },
        (actions) => {
          pendingActionsRef.current = actions
        },
        (tool, status) => {
          setToolStatus(status === 'running' ? (TOOL_LABELS[tool] ?? `${tool}...`) : null)
        },
        () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          const finalContent = accumulatedRef.current
          const { cleanContent, actions: inlineActions } = parseInlineActions(finalContent)
          const allActions = [...(pendingActionsRef.current ?? []), ...inlineActions]

          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: cleanContent,
            createdAt: new Date().toISOString(),
            actions: allActions.length > 0 ? allActions : undefined,
          }

          setMessages((prev) => [...prev, assistantMessage])
          setLastAssistantContent(cleanContent)
          setStreamingContent(null)
          setIsStreaming(false)
          setIsThinking(false)
          setToolStatus(null)
          abortRef.current = null
          pendingActionsRef.current = null
          firstTokenReceivedRef.current = false
        },
        () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          if (userAbortedRef.current) {
            userAbortedRef.current = false
            return
          }
          setIsStreaming(false)
          setIsThinking(false)
          setStreamingContent(null)
          setToolStatus(null)
          abortRef.current = null

          const errorMessage: Message = {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: "couldn't reach the server — try again?",
            createdAt: new Date().toISOString(),
            actions: [{ label: 'retry', value: text }],
            metadata: { isError: true },
          }
          setMessages((prev) => [...prev, errorMessage])
        },
      )

      abortRef.current = controller
    },
    [isStreaming, isThinking, isOnline, token],
  )

  const handleAction = useCallback(
    (value: string) => {
      if (value === '__pwa_install') {
        void triggerInstall()
        return
      }
      if (value === '__pwa_dismiss') {
        dismissPWA()
        return
      }
      if (value === '__pwa_ios') {
        const iosMessage: Message = {
          id: `pwa-ios-${Date.now()}`,
          role: 'assistant',
          content:
            'tap the share button at the bottom of Safari, then scroll down and tap "Add to Home Screen"',
          createdAt: new Date().toISOString(),
          metadata: { isSystem: true },
        }
        setMessages((prev) => [...prev, iosMessage])
        return
      }
      handleSend(value)
    },
    [handleSend, triggerInstall, dismissPWA],
  )

  const handleSignOut = useCallback(() => {
    void onSignOut()
  }, [onSignOut])

  const queuedSet = useMemo(() => new Set(queuedMessages), [queuedMessages])

  return (
    <div className="chat-screen">
      <div className="stars">
        <div className="stars-small" />
        <div className="stars-medium" />
        <div className="stars-large" />
      </div>
      <button
        className="mode-toggle-btn"
        type="button"
        onClick={() => setUIMode(uiMode === 'thought' ? 'chat' : 'thought')}
        aria-label={`Switch to ${uiMode === 'thought' ? 'chat' : 'thought'} mode`}
      >
        {uiMode === 'thought' ? 'chat view' : 'thought view'}
      </button>
      <button className="sign-out-btn" type="button" onClick={handleSignOut} aria-label="Sign out">
        sign out
      </button>
      <OfflineBanner visible={!isOnline} />
      <div className="chat-container">
        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          isThinking={isThinking}
          toolStatus={toolStatus}
          onAction={handleAction}
          queuedContents={queuedSet}
        />
        <InputBar onSend={handleSend} isStreaming={isStreaming || isThinking} onStop={handleStop} />
      </div>
      {showCat && <CatEasterEgg variant={variant} onDone={onCatDone} />}
    </div>
  )
}
