import { describe, it, expect } from 'vitest'
import { parseInlineActions } from './parseActions'

describe('parseInlineActions', () => {
  it('extracts a single action', () => {
    const result = parseInlineActions('hey [done](action:mark_done)')
    expect(result.actions).toEqual([{ label: 'done', value: 'mark_done' }])
    expect(result.cleanContent).toBe('hey')
  })

  it('extracts multiple actions', () => {
    const result = parseInlineActions(
      'pick one [done](action:done) [skip](action:skip) [something else](action:else)',
    )
    expect(result.actions).toHaveLength(3)
    expect(result.actions[0]).toEqual({ label: 'done', value: 'done' })
    expect(result.actions[1]).toEqual({ label: 'skip', value: 'skip' })
    expect(result.actions[2]).toEqual({ label: 'something else', value: 'else' })
  })

  it('returns empty actions when no patterns', () => {
    const result = parseInlineActions('just plain text')
    expect(result.actions).toEqual([])
    expect(result.cleanContent).toBe('just plain text')
  })

  it('does not consume regular markdown links', () => {
    const result = parseInlineActions('check [this link](https://example.com)')
    expect(result.actions).toEqual([])
    expect(result.cleanContent).toBe('check [this link](https://example.com)')
  })

  it('trims whitespace from cleaned content', () => {
    const result = parseInlineActions('  hello  [btn](action:x)  ')
    expect(result.cleanContent).toBe('hello')
  })

  it('handles empty content', () => {
    const result = parseInlineActions('')
    expect(result.actions).toEqual([])
    expect(result.cleanContent).toBe('')
  })
})
