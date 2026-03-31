interface DemoMessageProps {
  role: 'user' | 'assistant'
  content: string
}

export function DemoMessage({ role, content }: DemoMessageProps) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-user-bubble px-5 py-4 rounded-3xl rounded-tr-none text-[15px] leading-relaxed text-on-surface/80 font-light tracking-tight max-w-[85%]">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="pl-6 border-l-2 border-primary/10 text-[15px] leading-[1.8] text-on-surface-variant font-light">
      {content}
    </div>
  )
}
