import { describe, it, expect, vi, beforeEach } from 'vitest'
import { parseSSEEvent, fetchMessages } from './api'

describe('parseSSEEvent', () => {
  it('parses a token event', () => {
    const result = parseSSEEvent(JSON.stringify({ type: 'token', content: 'hello' }))
    expect(result).toEqual({ type: 'token', content: 'hello' })
  })

  it('parses a token event with empty string content', () => {
    const result = parseSSEEvent(JSON.stringify({ type: 'token', content: '' }))
    expect(result).toEqual({ type: 'token', content: '' })
  })

  it('parses an actions event', () => {
    const actions = JSON.stringify([{ label: 'done', value: 'done' }])
    const result = parseSSEEvent(JSON.stringify({ type: 'actions', content: actions }))
    expect(result).toEqual({ type: 'actions', content: actions })
  })

  it('parses a done event', () => {
    const result = parseSSEEvent(JSON.stringify({ type: 'done' }))
    expect(result).toEqual({ type: 'done' })
  })

  it('returns unknown for invalid JSON', () => {
    const result = parseSSEEvent('not json')
    expect(result).toEqual({ type: 'unknown' })
  })

  it('returns unknown for unrecognized event types', () => {
    const result = parseSSEEvent(JSON.stringify({ type: 'ping' }))
    expect(result).toEqual({ type: 'unknown' })
  })

  it('handles token event with undefined content', () => {
    const result = parseSSEEvent(JSON.stringify({ type: 'token' }))
    expect(result).toEqual({ type: 'token', content: undefined })
  })

  it('parses a tool_status running event', () => {
    const result = parseSSEEvent(
      JSON.stringify({ type: 'tool_status', tool: 'save_items', status: 'running' }),
    )
    expect(result).toEqual({ type: 'tool_status', tool: 'save_items', status: 'running' })
  })

  it('parses a tool_status done event', () => {
    const result = parseSSEEvent(
      JSON.stringify({ type: 'tool_status', tool: 'pick_next', status: 'done' }),
    )
    expect(result).toEqual({ type: 'tool_status', tool: 'pick_next', status: 'done' })
  })
})

describe('fetchMessages', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('unwraps the messages envelope and maps snake_case to camelCase', async () => {
    const mockResponse = {
      messages: [
        {
          id: 'msg-1',
          user_id: 'user-1',
          role: 'user' as const,
          content: 'hello',
          created_at: '2026-03-19T10:00:00Z',
          metadata: null,
        },
        {
          id: 'msg-2',
          user_id: 'user-1',
          role: 'assistant' as const,
          content: 'hey',
          created_at: '2026-03-19T10:00:01Z',
          metadata: { isSystem: true },
        },
      ],
      has_more: false,
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response)

    const result = await fetchMessages('test-token', 50)

    expect(result).toHaveLength(2)
    expect(result[0]!.id).toBe('msg-2')
    expect(result[0]!.createdAt).toBe('2026-03-19T10:00:01Z')
    expect(result[1]!.id).toBe('msg-1')
    expect(result[1]!.createdAt).toBe('2026-03-19T10:00:00Z')
    expect(result[0]!).not.toHaveProperty('created_at')
    expect(result[0]!).not.toHaveProperty('user_id')
  })

  it('reverses messages so oldest is first (backend returns DESC)', async () => {
    const mockResponse = {
      messages: [
        { id: 'newest', user_id: 'u', role: 'user' as const, content: 'b', created_at: '2026-03-19T11:00:00Z', metadata: null },
        { id: 'oldest', user_id: 'u', role: 'user' as const, content: 'a', created_at: '2026-03-19T10:00:00Z', metadata: null },
      ],
      has_more: false,
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response)

    const result = await fetchMessages('test-token')

    expect(result[0]!.id).toBe('oldest')
    expect(result[1]!.id).toBe('newest')
  })

  it('returns empty array when no messages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ messages: [], has_more: false }),
    } as Response)

    const result = await fetchMessages('test-token')
    expect(result).toEqual([])
  })

  it('converts null metadata to undefined', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        messages: [{ id: '1', user_id: 'u', role: 'user', content: 'hi', created_at: '2026-01-01T00:00:00Z', metadata: null }],
        has_more: false,
      }),
    } as Response)

    const result = await fetchMessages('test-token')
    expect(result[0]!.metadata).toBeUndefined()
  })

  it('throws on non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 401,
    } as Response)

    await expect(fetchMessages('bad-token')).rejects.toThrow('Failed to fetch messages: 401')
  })
})
