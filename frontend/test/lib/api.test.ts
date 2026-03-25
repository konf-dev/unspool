import { describe, it, expect } from 'vitest'
import { parseSSEEvents } from '@/lib/api'

describe('parseSSEEvents', () => {
  it('parses token event', () => {
    const events = parseSSEEvents('{"type":"token","content":"hello"}')
    expect(events).toEqual([{ type: 'token', content: 'hello' }])
  })

  it('parses done event', () => {
    const events = parseSSEEvents('{"type":"done"}')
    expect(events).toEqual([{ type: 'done' }])
  })

  it('parses tool_start event', () => {
    const events = parseSSEEvents('{"type":"tool_start","calls":["query_graph"]}')
    expect(events).toEqual([
      { type: 'tool_status', tool: 'query_graph', status: 'running' },
    ])
  })

  it('parses tool_end event', () => {
    const events = parseSSEEvents('{"type":"tool_end","name":"query_graph"}')
    expect(events).toEqual([
      { type: 'tool_status', tool: 'query_graph', status: 'done' },
    ])
  })

  it('parses error event', () => {
    const events = parseSSEEvents('{"type":"error","content":"limit reached"}')
    expect(events).toEqual([{ type: 'error', content: 'limit reached' }])
  })

  it('returns unknown for malformed data', () => {
    const events = parseSSEEvents('not json at all')
    expect(events).toEqual([{ type: 'unknown' }])
  })

  it('handles unknown event type', () => {
    const events = parseSSEEvents('{"type":"foo"}')
    expect(events).toEqual([{ type: 'unknown' }])
  })
})
