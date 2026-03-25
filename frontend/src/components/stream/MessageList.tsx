import type { Message, ActionButton } from '@/types'
import { useScrollAnchor } from '@/hooks/useScrollAnchor'
import { UserThought } from './UserThought'
import { Reflection } from './Reflection'
import { StreamingText } from './StreamingText'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ToolStatus } from './ToolStatus'

interface MessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  isThinking: boolean
  toolStatus: string | null
  onAction: (action: ActionButton) => void
}

export function MessageList({
  messages,
  streamingContent,
  isStreaming,
  isThinking,
  toolStatus,
  onAction,
}: MessageListProps) {
  const { scrollRef, isAtBottom, scrollToBottom } = useScrollAnchor([
    messages.length,
    streamingContent,
    isThinking,
  ])

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto px-6 no-scrollbar"
        role="log"
        aria-live="polite"
        aria-label="Message stream"
      >
        <div className="max-w-[640px] mx-auto space-y-8 pt-16 pb-4">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4">
              <h1 className="text-on-surface-variant font-light text-lg tracking-tight leading-relaxed opacity-80">
                just start typing — I'll remember everything
              </h1>
              <p className="text-on-surface-variant/40 text-sm tracking-wide">
                try: dump everything on your mind right now
              </p>
            </div>
          )}

          {messages.map((message) =>
            message.role === 'user' ? (
              <UserThought key={message.id} message={message} />
            ) : (
              <Reflection key={message.id} message={message} onAction={onAction} />
            ),
          )}

          {toolStatus && <ToolStatus tool={toolStatus} />}
          {isThinking && !toolStatus && !streamingContent && <ThinkingIndicator />}
          {streamingContent && <StreamingText content={streamingContent} />}
        </div>
      </div>

      {!isAtBottom && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-surface-container-high text-on-surface-variant text-xs px-4 py-2 rounded-full shadow-lg transition-all duration-300 hover:bg-surface-bright"
          aria-label="Scroll to latest messages"
        >
          new messages
        </button>
      )}
    </div>
  )
}
