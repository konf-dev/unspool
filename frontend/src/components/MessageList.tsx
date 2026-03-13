import { useRef, useState, useCallback } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import type { Message } from '../types'
import { MessageBubble } from './MessageBubble'
import { StreamingText } from './StreamingText'
import { TypingIndicator } from './TypingIndicator'
import './MessageList.css'

interface MessageListProps {
  messages: Message[]
  streamingContent: string | null
  isStreaming: boolean
  isThinking: boolean
  onAction: (value: string) => void
  onLoadMore?: () => void
}

export function MessageList({
  messages,
  streamingContent,
  isStreaming,
  isThinking,
  onAction,
  onLoadMore,
}: MessageListProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [showJumpToBottom, setShowJumpToBottom] = useState(false)

  const showStreamingBubble =
    isStreaming && !isThinking && streamingContent !== null

  const allMessages: Message[] = [
    ...messages,
    ...(showStreamingBubble
      ? [
          {
            id: 'streaming',
            role: 'assistant' as const,
            content: streamingContent,
            createdAt: new Date().toISOString(),
          },
        ]
      : []),
  ]

  const handleAtBottomStateChange = useCallback(
    (atBottom: boolean) => {
      setShowJumpToBottom(!atBottom && (isStreaming || isThinking))
    },
    [isStreaming, isThinking],
  )

  const handleJumpToBottom = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({
      index: allMessages.length - 1,
      behavior: 'smooth',
    })
  }, [allMessages.length])

  return (
    <div className="message-list-container" role="log" aria-live="polite">
      <Virtuoso
        ref={virtuosoRef}
        data={allMessages}
        followOutput="smooth"
        startReached={onLoadMore}
        atBottomStateChange={handleAtBottomStateChange}
        atBottomThreshold={100}
        itemContent={(index, message) => (
          <div
            style={{
              paddingTop:
                index === 0 ? 'var(--spacing-lg)' : 'var(--spacing-message-gap)',
            }}
          >
            {message.id === 'streaming' ? (
              <div className="message-row assistant">
                <div>
                  <div className="message-bubble assistant">
                    <StreamingText content={message.content} />
                  </div>
                </div>
              </div>
            ) : (
              <MessageBubble
                message={message}
                isLatest={index === allMessages.length - 1}
                onAction={onAction}
              />
            )}
          </div>
        )}
        components={{
          Footer: () => (
            <>
              {isThinking && (
                <div style={{ paddingTop: 'var(--spacing-message-gap)', paddingLeft: 'var(--spacing-md)' }}>
                  <TypingIndicator />
                </div>
              )}
              <div className="message-list-spacer" />
            </>
          ),
        }}
      />
      <button
        className={`jump-to-bottom ${showJumpToBottom ? 'visible' : ''}`}
        type="button"
        onClick={handleJumpToBottom}
        aria-label="Jump to latest message"
      >
        jump to latest
      </button>
    </div>
  )
}
