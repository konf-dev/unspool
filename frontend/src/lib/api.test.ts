import { describe, it, expect } from 'vitest'
import { parseSSEEvent } from './api'

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
})
