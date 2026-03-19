import type { ActionButton } from '../types'

const ACTION_PATTERN = /\[([^\]]+)\]\(action:([^)]+)\)/g

export function parseInlineActions(content: string): {
  cleanContent: string
  actions: ActionButton[]
} {
  const actions: ActionButton[] = []
  const cleanContent = content.replace(ACTION_PATTERN, (_match, label: string, value: string) => {
    actions.push({ label: label.trim(), value: value.trim() })
    return ''
  })
  return { cleanContent: cleanContent.trim(), actions }
}
