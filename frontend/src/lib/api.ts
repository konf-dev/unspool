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
  type: 'token' | 'actions' | 'tool_status' | 'done' | 'error' | 'unknown'
  content?: string
  tool?: string
  status?: 'running' | 'done'
}

export function parseSSEEvents(data: string): ParsedSSEEvent[] {
  // SSE can bundle multiple data: lines in one chunk.
  // Each data line starts with "data: " and ends with "\n\n" usually,
  // but fetchEventSource gives us the decoded data content.
  // If multiple events were in one chunk, they might be separated by newlines
  // or just be multiple JSON objects if the server didn't use standard SSE format correctly.
  
  const events: ParsedSSEEvent[] = []
  
  // Try parsing the whole thing as one JSON first
  try {
    const parsed = JSON.parse(data)
    events.push(mapToSSEEvent(parsed))
    return events
  } catch {
    // If it fails, maybe it's multiple JSONs. 
    // Brute force split by }{ and fix them
    const parts = data.split('}\n\n{')
    if (parts.length > 1) {
      for (let i = 0; i < parts.length; i++) {
        let p = parts[i] as string
        if (i > 0) p = '{' + p
        if (i < parts.length - 1) p = p + '}'
        try {
          events.push(mapToSSEEvent(JSON.parse(p)))
        } catch {
          // ignore malformed
        }
      }
      return events
    }
  }
  
  return [{ type: 'unknown' }]
}

function mapToSSEEvent(parsed: any): ParsedSSEEvent {
  switch (parsed.type) {
    case 'token':
      return { type: 'token', content: parsed.content }
    case 'actions':
      return { type: 'actions', content: parsed.content }
    case 'tool_status':
      return {
        type: 'tool_status',
        tool: parsed.tool,
        status: parsed.status,
      }
    case 'error':
      return { type: 'error', content: parsed.content }
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
  onToolStatus?: (tool: string, status: 'running' | 'done') => void,
  onDone?: () => void,
  onError?: (err: any) => void,
): AbortController {
  if (useMocks()) {
    return mockSendMessage(message, onToken, onActions, onDone)
  }

  const controller = new AbortController()
  let streamDone = false

  void fetchEventSource(`${getApiUrl()}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
    signal: controller.signal,
    async onopen(response) {
      if (response.ok) {
        return
      }
      if (response.status === 429) {
        const body = await response.json()
        const err = new Error(body.detail || 'Daily limit reached')
        ;(err as any).status = 429
        onError?.(err)
        controller.abort()
        return
      }
      const err = new Error(`Request failed with status ${response.status}`)
      onError?.(err)
      controller.abort()
    },
    onmessage(event) {
      const events = parseSSEEvents(event.data)

      for (const parsed of events) {
        switch (parsed.type) {
          case 'token':
            if (parsed.content !== undefined) onToken(parsed.content)
            break
          case 'actions':
            if (onActions && parsed.content) {
              try {
                const actions = JSON.parse(parsed.content) as ActionButton[]
                onActions(actions)
              } catch {
                // ignore
              }
            }
            break
          case 'tool_status':
            if (onToolStatus && parsed.tool && parsed.status) {
              onToolStatus(parsed.tool, parsed.status)
            }
            break
          case 'error':
            if (onError && parsed.content) {
              onError(new Error(parsed.content))
            }
            break
          case 'done':
            streamDone = true
            onDone?.()
            break
        }
      }
    },
    onclose() {
      if (streamDone) return
      // Abnormal close before "done" — never retry. Each chat message is a
      // one-shot request; retrying would duplicate the user message in the DB.
      onError?.(new Error('connection lost'))
      throw new Error('stream closed')
    },
    onerror(err) {
      if (err.status === 429) {
        throw err // prevent retry
      }
      if (!streamDone) {
        onError?.(err)
      }
      throw err // prevent retry
    },
    openWhenHidden: true,
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
