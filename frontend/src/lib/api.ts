import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { ActionButton, Message, ParsedSSEEvent } from '@/types'

function getApiUrl(): string {
  return (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'
}

function mapToSSEEvent(parsed: Record<string, unknown>): ParsedSSEEvent {
  switch (parsed.type) {
    case 'token':
      return { type: 'token', content: parsed.content as string }
    case 'actions':
      return { type: 'actions', content: parsed.content as string }
    case 'tool_start':
      return {
        type: 'tool_status',
        tool: ((parsed.calls as string[]) ?? [])[0] ?? 'thinking',
        status: 'running',
      }
    case 'tool_end':
      return {
        type: 'tool_status',
        tool: parsed.name as string,
        status: 'done',
      }
    case 'error':
      return { type: 'error', content: parsed.content as string }
    case 'done':
      return { type: 'done' }
    default:
      return { type: 'unknown' }
  }
}

export function parseSSEEvents(data: string): ParsedSSEEvent[] {
  try {
    const parsed = JSON.parse(data) as Record<string, unknown>
    return [mapToSSEEvent(parsed)]
  } catch {
    // data may contain multiple concatenated JSON objects — parse each one
    const events: ParsedSSEEvent[] = []
    let depth = 0
    let start = -1
    for (let i = 0; i < data.length; i++) {
      if (data[i] === '{') {
        if (depth === 0) start = i
        depth++
      } else if (data[i] === '}') {
        depth--
        if (depth === 0 && start >= 0) {
          try {
            events.push(mapToSSEEvent(JSON.parse(data.slice(start, i + 1)) as Record<string, unknown>))
          } catch {
            // skip malformed fragment
          }
          start = -1
        }
      }
    }
    return events.length > 0 ? events : [{ type: 'unknown' }]
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
  onError?: (err: unknown) => void,
): AbortController {
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
      if (response.ok) return

      if (response.status === 429) {
        const body = (await response.json()) as { detail?: string }
        const err = new Error(body.detail ?? 'Daily limit reached')
        ;(err as Error & { status?: number }).status = 429
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
      // Don't retry — each chat message is a one-shot request.
      // Retrying would duplicate the user message in the DB.
      onError?.(new Error('connection lost'))
      throw new Error('stream closed') // prevents fetchEventSource retry
    },
    onerror(err: unknown) {
      if (!streamDone) {
        onError?.(err)
      }
      throw err // prevents fetchEventSource retry
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
      role: (msg.role === 'assistant' ? 'reflection' : msg.role) as 'user' | 'reflection',
      content: msg.content,
      createdAt: msg.created_at,
      metadata: msg.metadata ?? undefined,
    }))
    .reverse()
}

export async function fetchLatestPlate(
  token: string,
): Promise<{ items: Array<{ id: string; content: string; deadline?: string }> } | null> {
  // Fetch just the latest message to extract plate metadata
  const messages = await fetchMessages(token, 1)
  const latest = messages[messages.length - 1]
  if (latest?.metadata?.plate) {
    return latest.metadata.plate as { items: Array<{ id: string; content: string; deadline?: string }> }
  }
  return null
}

export { getApiUrl }
