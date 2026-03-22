import './StreamingText.css'

interface StreamingTextProps {
  content: string
}

export function StreamingText({ content }: StreamingTextProps) {
  return (
    <div className="streaming-text">
      <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
      <span className="streaming-cursor" />
    </div>
  )
}
