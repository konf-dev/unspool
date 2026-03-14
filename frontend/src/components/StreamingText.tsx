import Markdown from 'markdown-to-jsx'
import './StreamingText.css'

interface StreamingTextProps {
  content: string
}

export function StreamingText({ content }: StreamingTextProps) {
  return (
    <div className="streaming-text markdown-content">
      <Markdown>{content}</Markdown>
      <span className="streaming-cursor" />
    </div>
  )
}
