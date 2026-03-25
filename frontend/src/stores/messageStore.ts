import { create } from 'zustand'
import type { Message, ActionButton } from '@/types'
import { sendMessage as apiSendMessage, fetchMessages as apiFetchMessages, fetchLatestPlate } from '@/lib/api'
import { usePlateStore } from '@/stores/plateStore'
import { parseInlineActions } from '@/lib/parseActions'

const SESSION_KEY = 'unspool-session-id'
const QUEUE_KEY = 'unspool-queue'

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function loadQueue(): Array<{ id: string; content: string }> {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) ?? '[]') as Array<{
      id: string
      content: string
    }>
  } catch {
    return []
  }
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

  sendMessage: (content: string, token: string) => void
  stopStreaming: () => void
  fetchHistory: (token: string, before?: string) => Promise<void>
  handleAction: (action: ActionButton, token: string) => void
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
    }))

    if (!navigator.onLine) {
      const queue = [...get().queue, { id, content }]
      localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
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
        if (rafId === null) {
          rafId = requestAnimationFrame(() => {
            set({ streamingContent: accumulated, isThinking: false })
            rafId = null
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

        // Refresh plate data from the persisted message metadata
        void fetchLatestPlate(token).then((plate) => {
          if (plate?.items) {
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
        }).catch(() => {})
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
    )

    set({ _abortController: controller })
  },

  stopStreaming: () => {
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
      set((state) => ({
        messages: before ? [...messages, ...state.messages] : messages,
        hasMore: messages.length >= 50,
      }))
    } finally {
      set({ _isFetching: false })
    }
  },

  handleAction: (action: ActionButton, token: string) => {
    get().sendMessage(action.value, token)
  },

  flushQueue: (token: string) => {
    const queue = get().queue
    if (queue.length === 0 || get().isStreaming) return

    const next = queue[0]
    if (!next) return

    const remaining = queue.slice(1)
    localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining))
    set({ queue: remaining })

    get().sendMessage(next.content, token)
  },
}))
