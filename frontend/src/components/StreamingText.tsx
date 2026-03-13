import './StreamingText.css'

interface StreamingTextProps {
  content: string
}

export function StreamingText({ content }: StreamingTextProps) {
  return (
    <span className="streaming-text">
      {content}
      <span className="streaming-cursor" />
    </span>
  )
}
