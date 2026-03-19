import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { ActionButton, Message } from '../types'
import { mockSendMessage, mockFetchMessages } from './mock'

function getApiUrl(): string {
  return (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'
}

function useMocks(): boolean {
  return import.meta.env.VITE_USE_MOCKS === 'true'
}

export interface ParsedSSEEvent {
  type: 'token' | 'actions' | 'done' | 'unknown'
  content?: string
}

export function parseSSEEvent(data: string): ParsedSSEEvent {
  let parsed: { type: string; content?: string }
  try {
    parsed = JSON.parse(data) as { type: string; content?: string }
  } catch {
    return { type: 'unknown' }
  }

  switch (parsed.type) {
    case 'token':
      return { type: 'token', content: parsed.content }
    case 'actions':
      return { type: 'actions', content: parsed.content }
    case 'done':
      return { type: 'done' }
    default:
      return { type: 'unknown' }
  }
}

export function sendMessage(
  message: string,
  sessionId: string,
  token: string,
  onToken: (token: string) => void,
  onActions?: (actions: ActionButton[]) => void,
  onDone?: () => void,
  onError?: (err: unknown) => void,
): AbortController {
  if (useMocks()) {
    return mockSendMessage(message, onToken, onActions, onDone)
  }

  const controller = new AbortController()

  void fetchEventSource(`${getApiUrl()}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal: controller.signal,
    onmessage(event) {
      const parsed = parseSSEEvent(event.data)

      switch (parsed.type) {
        case 'token':
          if (parsed.content !== undefined) onToken(parsed.content)
          break
        case 'actions':
          if (onActions && parsed.content) {
            const actions = JSON.parse(parsed.content) as ActionButton[]
            onActions(actions)
          }
          break
        case 'done':
          onDone?.()
          break
      }
    },
    onerror(err) {
      console.error('SSE error:', err)
      onError?.(err)
      throw err
    },
  })

  return controller
}

interface MessagesResponse {
  messages: Array<{
    id: string
    user_id: string
    role: 'user' | 'assistant'
    content: string
    created_at: string
    metadata: Record<string, unknown> | null
  }>
  has_more: boolean
}

export async function fetchMessages(
  token: string,
  limit?: number,
  before?: string,
): Promise<Message[]> {
  if (useMocks()) {
    return mockFetchMessages()
  }

  const params = new URLSearchParams()
  if (limit !== undefined) params.set('limit', String(limit))
  if (before) params.set('before', before)

  const url = `${getApiUrl()}/api/messages?${params.toString()}`
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch messages: ${response.status}`)
  }

  const data = (await response.json()) as MessagesResponse
  return data.messages
    .map((msg) => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      createdAt: msg.created_at,
      metadata: msg.metadata ?? undefined,
    }))
    .reverse()
}

export { getApiUrl }
