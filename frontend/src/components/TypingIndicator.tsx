import './TypingIndicator.css'

export function TypingIndicator() {
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
