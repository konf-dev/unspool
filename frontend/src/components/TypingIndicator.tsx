import type { UIMode } from '../types'
import './TypingIndicator.css'

interface TypingIndicatorProps {
  mode?: UIMode
}

export function TypingIndicator({ mode = 'chat' }: TypingIndicatorProps) {
  if (mode === 'thought') {
    return (
      <div className="message-row assistant thought-mode" role="status">
        <div className="thinking-dot-wrapper">
          <span className="thinking-dot" />
        </div>
      </div>
    )
  }

  return (
    <div className="message-row assistant" role="status">
      <div className="typing-bubble">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  )
}
