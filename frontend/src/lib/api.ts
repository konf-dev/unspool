import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { ActionButton, Message } from '../types'
import { mockSendMessage, mockFetchMessages } from './mock'

function getApiUrl(): string {
  return (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'
}

function useMocks(): boolean {
  return import.meta.env.VITE_USE_MOCKS === 'true'
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
      let parsed: { type: string; content?: string }
      try {
        parsed = JSON.parse(event.data) as { type: string; content?: string }
      } catch {
        return
      }

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

  return (await response.json()) as Message[]
}

export { getApiUrl }
