import { describe, it, expect } from 'vitest'
import { parseInlineActions } from '@/lib/parseActions'

describe('parseInlineActions', () => {
  it('extracts single action from content', () => {
    const result = parseInlineActions('message [done](action:done)')
    expect(result.cleanContent).toBe('message')
    expect(result.actions).toEqual([{ label: 'done', value: 'done' }])
  })

  it('extracts multiple actions', () => {
    const result = parseInlineActions(
      'choose: [done](action:mark_done) [skip](action:skip_item)',
    )
    expect(result.actions).toHaveLength(2)
    expect(result.actions[0]).toEqual({ label: 'done', value: 'mark_done' })
    expect(result.actions[1]).toEqual({ label: 'skip', value: 'skip_item' })
  })

  it('returns empty actions for plain text', () => {
    const result = parseInlineActions('just a normal message')
    expect(result.cleanContent).toBe('just a normal message')
    expect(result.actions).toEqual([])
  })

  it('trims whitespace from content after removal', () => {
    const result = parseInlineActions('[done](action:done) ')
    expect(result.cleanContent).toBe('')
    expect(result.actions).toHaveLength(1)
  })

  it('handles action with spaces in label', () => {
    const result = parseInlineActions('[mark as done](action:done)')
    expect(result.actions[0]).toEqual({ label: 'mark as done', value: 'done' })
  })
})
