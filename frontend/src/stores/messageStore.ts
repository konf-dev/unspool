import { create } from 'zustand'
import type { Message, ActionButton } from '@/types'
import { sendMessage as apiSendMessage, fetchMessages as apiFetchMessages, deleteAccount } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { usePlateStore } from '@/stores/plateStore'
import { parseInlineActions } from '@/lib/parseActions'

const SESSION_KEY = 'unspool-session-id'
const QUEUE_KEY = 'unspool-queue'

function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* quota exceeded in Safari private */ }
}

function getSessionId(): string {
  let id = safeGetItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    safeSetItem(SESSION_KEY, id)
  }
  return id
}

function loadQueue(): Array<{ id: string; content: string }> {
  try {
    return JSON.parse(safeGetItem(QUEUE_KEY) ?? '[]') as Array<{
      id: string
      content: string
    }>
  } catch {
    return []
  }
}

/** Read the freshest auth token — avoids stale closures. */
function getFreshToken(): string | null {
  return useAuthStore.getState().token
}

interface MessageStore {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  isThinking: boolean
  toolStatus: string | null
  pendingActions: ActionButton[] | null
  queue: Array<{ id: string; content: string }>
  hasMore: boolean
  _abortController: AbortController | null
  _isFetching: boolean
  _streamAborted: boolean

  sendMessage: (content: string, token: string) => void
  stopStreaming: () => void
  fetchHistory: (token: string, before?: string) => Promise<void>
  handleAction: (action: ActionButton, token: string) => void | Promise<void>
  flushQueue: (token: string) => void
}

export const useMessageStore = create<MessageStore>((set, get) => ({
  messages: [],
  streamingContent: '',
  isStreaming: false,
  isThinking: false,
  toolStatus: null,
  pendingActions: null,
  queue: loadQueue(),
  hasMore: true,
  _abortController: null,
  _isFetching: false,
  _streamAborted: false,

  sendMessage: (content: string, token: string) => {
    if (get().isStreaming) return // Prevent concurrent sends

    const id = crypto.randomUUID()
    const userMessage: Message = {
      id,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
      status: 'sending',
    }

    set((state) => ({
      messages: [...state.messages, userMessage],
      isThinking: true,
      isStreaming: true,
      streamingContent: '',
      pendingActions: null,
      toolStatus: null,
      _streamAborted: false,
    }))

    if (!navigator.onLine) {
      const queue = [...get().queue, { id, content }]
      safeSetItem(QUEUE_KEY, JSON.stringify(queue))
      set((state) => ({
        queue,
        isThinking: false,
        isStreaming: false,
        messages: state.messages.map((m) =>
          m.id === id ? { ...m, status: 'queued' as const } : m,
        ),
      }))
      return
    }

    let accumulated = ''
    let rafId: number | null = null

    const controller = apiSendMessage(
      content,
      getSessionId(),
      token,
      (tokenStr: string) => {
        accumulated += tokenStr
        // #6: Check abort flag before scheduling RAF
        if (get()._streamAborted) return
        if (rafId === null) {
          rafId = requestAnimationFrame(() => {
            rafId = null
            // #6: Double-check abort flag inside RAF callback
            if (!get()._streamAborted) {
              set({ streamingContent: accumulated, isThinking: false })
            }
          })
        }
      },
      (actions: ActionButton[]) => {
        set({ pendingActions: actions })
      },
      (tool: string, status: 'running' | 'done') => {
        set({ toolStatus: status === 'running' ? tool : null })
      },
      () => {
        if (rafId !== null) cancelAnimationFrame(rafId)
        const finalContent = accumulated
        const { cleanContent, actions } = parseInlineActions(finalContent)
        const reflection: Message = {
          id: crypto.randomUUID(),
          role: 'reflection',
          content: cleanContent,
          createdAt: new Date().toISOString(),
          actions: [...(get().pendingActions ?? []), ...actions],
        }
        set((state) => ({
          messages: [
            ...state.messages.map((m) =>
              m.id === id ? { ...m, status: 'sent' as const } : m,
            ),
            reflection,
          ],
          streamingContent: '',
          isStreaming: false,
          isThinking: false,
          toolStatus: null,
          _abortController: null,
          pendingActions: null,
        }))

        // #3: After stream completes, flush next queued message if any
        const queue = get().queue
        if (queue.length > 0) {
          const freshToken = getFreshToken()
          if (freshToken) {
            // Small delay to avoid back-to-back sends
            setTimeout(() => get().flushQueue(freshToken), 500)
          }
        }
      },
      (err: unknown) => {
        if (rafId !== null) cancelAnimationFrame(rafId)
        const errorContent =
          err instanceof Error ? err.message : 'Something went wrong'
        const isRateLimit =
          err instanceof Error && (err as Error & { status?: number }).status === 429
        const errorMessage: Message = {
          id: crypto.randomUUID(),
          role: 'reflection',
          content: isRateLimit
            ? errorContent
            : "I lost my train of thought. Let's try that again.",
          createdAt: new Date().toISOString(),
          actions: isRateLimit ? undefined : [{ label: 'retry', value: content }],
          metadata: { type: 'error' },
        }
        set((state) => ({
          messages: [...state.messages, errorMessage],
          streamingContent: '',
          isStreaming: false,
          isThinking: false,
          toolStatus: null,
          _abortController: null,
          pendingActions: null,
        }))
      },
      // Handle plate data from SSE stream — no more fetchLatestPlate race
      (items) => {
        usePlateStore.getState().setPlate(
          items.map((p) => ({
            id: p.id,
            label: p.content,
            deadline: p.deadline,
            hasDeadline: !!p.deadline,
            isDone: false,
          })),
        )
      },
    )

    set({ _abortController: controller })
  },

  stopStreaming: () => {
    // #6: Set abort flag so pending RAF callbacks are no-ops
    set({ _streamAborted: true })

    const controller = get()._abortController
    if (controller) controller.abort()

    const content = get().streamingContent
    if (content) {
      const { cleanContent, actions } = parseInlineActions(content)
      const reflection: Message = {
        id: crypto.randomUUID(),
        role: 'reflection',
        content: cleanContent,
        createdAt: new Date().toISOString(),
        actions: [...(get().pendingActions ?? []), ...actions],
      }
      set((state) => ({
        messages: [...state.messages, reflection],
      }))
    }

    set({
      streamingContent: '',
      isStreaming: false,
      isThinking: false,
      toolStatus: null,
      _abortController: null,
      pendingActions: null,
    })
  },

  fetchHistory: async (token: string, before?: string) => {
    if (get()._isFetching) return // Prevent concurrent fetches
    set({ _isFetching: true })

    try {
      const messages = await apiFetchMessages(token, 50, before)
      if (messages.length === 0) {
        set({ hasMore: false })
        return
      }
      set((state) => {
        if (before) {
          // #11: Deduplicate by id when prepending paginated results
          const existingIds = new Set(state.messages.map((m) => m.id))
          const newMessages = messages.filter((m) => !existingIds.has(m.id))
          return {
            messages: [...newMessages, ...state.messages],
            hasMore: messages.length >= 50,
          }
        }
        return {
          messages,
          hasMore: messages.length >= 50,
        }
      })

      // On initial load, populate plate from the latest message metadata
      if (!before) {
        const allMessages = get().messages
        for (let i = allMessages.length - 1; i >= 0; i--) {
          const m = allMessages[i]
          if (m?.metadata?.plate) {
            const plate = m.metadata.plate as {
              items?: Array<{ id: string; content: string; deadline?: string }>
            }
            if (plate.items) {
              usePlateStore.getState().setPlate(
                plate.items.map((p) => ({
                  id: p.id,
                  label: p.content,
                  deadline: p.deadline,
                  hasDeadline: !!p.deadline,
                  isDone: false,
                })),
              )
            }
            break
          }
        }
      }
    } finally {
      set({ _isFetching: false })
    }
  },

  handleAction: async (action: ActionButton, token: string) => {
    if (action.value === 'delete_account') {
      try {
        const response = await deleteAccount(token)
        if (!response.ok) {
          const body = await response.text()
          console.error('Account deletion failed:', response.status, body)
          return
        }
        // Data deleted — now sign out (token is still valid until signOut)
        useAuthStore.getState().signOut()
      } catch (err) {
        console.error('Account deletion error:', err)
      }
      return
    }
    if (action.value === 'cancel') {
      return
    }
    get().sendMessage(action.value, token)
  },

  flushQueue: (token: string) => {
    const queue = get().queue
    if (queue.length === 0 || get().isStreaming) return

    const next = queue[0]
    if (!next) return

    const remaining = queue.slice(1)
    safeSetItem(QUEUE_KEY, JSON.stringify(remaining))
    set({ queue: remaining })

    get().sendMessage(next.content, token)
  },
}))
