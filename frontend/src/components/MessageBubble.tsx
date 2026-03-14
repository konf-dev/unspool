import { useState, useMemo } from 'react'
import Markdown from 'markdown-to-jsx'
import type { Message } from '../types'
import { COMPLETION_KEYWORDS } from '../lib/constants'
import { ActionButtons } from './ActionButtons'
import './MessageBubble.css'

function isCompletionMessage(content: string): boolean {
  const lower = content.toLowerCase()
  return COMPLETION_KEYWORDS.some((kw) => lower.includes(kw))
}

interface MessageBubbleProps {
  message: Message
  isLatest: boolean
  onAction: (value: string) => void
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then

  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function MessageBubble({
  message,
  isLatest,
  onAction,
}: MessageBubbleProps) {
  const [showTimestamp, setShowTimestamp] = useState(false)

  const showDoneDot = useMemo(
    () => message.role === 'assistant' && isCompletionMessage(message.content),
    [message.role, message.content],
  )

  const isError = message.metadata?.isError === true
  const isSystem = message.metadata?.isSystem === true

  if (isSystem) {
    return (
      <div className="message-row system">
        <div className="system-message">
          <span className="system-message-content">{message.content}</span>
          {message.actions && message.actions.length > 0 && (
            <ActionButtons actions={message.actions} onAction={onAction} />
          )}
        </div>
      </div>
    )
  }

  const bubbleClasses = [
    'message-bubble',
    message.role,
    isLatest ? 'latest' : '',
    isError ? 'error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={`message-row ${message.role}`}>
      <div>
        <div
          className={bubbleClasses}
          onClick={() => setShowTimestamp((prev) => !prev)}
        >
          {message.role === 'assistant' ? (
            <div className="message-bubble-content markdown-content">
              <Markdown>{message.content}</Markdown>
            </div>
          ) : (
            <span className="message-bubble-content">{message.content}</span>
          )}
          {showDoneDot && <span className="done-dot" aria-hidden="true" />}
        </div>
        {message.actions && message.actions.length > 0 && (
          <ActionButtons actions={message.actions} onAction={onAction} />
        )}
        <div
          className={`message-timestamp ${showTimestamp ? 'visible' : ''}`}
        >
          {formatRelativeTime(message.createdAt)}
        </div>
      </div>
    </div>
  )
}
