interface DemoMessageProps {
  role: 'user' | 'assistant'
  content: string
}

export function DemoMessage({ role, content }: DemoMessageProps) {
  if (role === 'user') {
    return (
      <div className="text-[15px] leading-relaxed text-on-surface/80 font-light tracking-tight">
        {content}
      </div>
    )
  }

  return (
    <div className="pl-6 text-[15px] leading-[1.8] text-on-surface-variant font-light">
      {content}
    </div>
  )
}
