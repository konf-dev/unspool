import { useRef, useState, useCallback, useEffect } from 'react'
import type { Message } from '../types'
import { useUIMode } from '../contexts/UIMode'
import { MessageBubble } from './MessageBubble'
import { StreamingText } from './StreamingText'
import { TypingIndicator } from './TypingIndicator'
import './MessageList.css'

interface MessageListProps {
  messages: Message[]
  streamingContent: string | null
  isStreaming: boolean
  isThinking: boolean
  toolStatus: string | null
  onAction: (value: string) => void
  queuedContents?: Set<string>
}

export function MessageList({
  messages,
  streamingContent,
  isStreaming,
  isThinking,
  toolStatus,
  onAction,
  queuedContents,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [showJumpToBottom, setShowJumpToBottom] = useState(false)
  const { uiMode } = useUIMode()

  const showStreamingBubble = isStreaming && !isThinking && streamingContent !== null
  const thoughtClass = uiMode === 'thought' ? 'thought-mode' : ''

  const checkAtBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
    setIsAtBottom(atBottom)
    setShowJumpToBottom(!atBottom)
  }, [])

  useEffect(() => {
    if (isAtBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamingContent, isThinking, isAtBottom])

  const handleJumpToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [])

  return (
    <div className="message-list-container" role="log" aria-live="polite">
      <div ref={scrollRef} className="message-list-scroll" onScroll={checkAtBottom}>
        <div className="message-list-inner">
          {messages.map((message, index) => (
            <div
              key={message.id}
              style={{
                paddingTop: index === 0 ? 'var(--spacing-lg)' : 'var(--spacing-message-gap)',
              }}
            >
              <MessageBubble
                message={message}
                isLatest={!showStreamingBubble && !isThinking && index === messages.length - 1}
                isQueued={
                  message.role === 'user' &&
                  queuedContents !== undefined &&
                  queuedContents.has(message.content)
                }
                onAction={onAction}
              />
            </div>
          ))}
          {showStreamingBubble && (
            <div style={{ paddingTop: 'var(--spacing-message-gap)' }}>
              <div className={`message-row assistant ${thoughtClass}`}>
                <div>
                  <div className={`message-bubble assistant ${thoughtClass}`}>
                    <StreamingText content={streamingContent} />
                  </div>
                </div>
              </div>
            </div>
          )}
          {toolStatus && (
            <div style={{ paddingTop: 'var(--spacing-xs)', paddingLeft: 'var(--spacing-md)' }}>
              <span className="tool-status-label">{toolStatus}</span>
            </div>
          )}
          {isThinking && (
            <div
              style={{
                paddingTop: 'var(--spacing-message-gap)',
                paddingLeft: 'var(--spacing-md)',
              }}
            >
              <TypingIndicator mode={uiMode} />
            </div>
          )}
          <div className="message-list-spacer" />
        </div>
      </div>
      <button
        className={`jump-to-bottom ${showJumpToBottom ? 'visible' : ''}`}
        type="button"
        onClick={handleJumpToBottom}
        aria-label="Jump to latest message"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M12 5V19M5 12L12 19L19 12"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  )
}
