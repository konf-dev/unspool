import { TOOL_LABELS } from '@/lib/constants'

interface ToolStatusProps {
  tool: string
}

export function ToolStatus({ tool }: ToolStatusProps) {
  const label = TOOL_LABELS[tool] ?? `${tool}...`

  return (
    <div className="pl-6 py-1 animate-fade-in">
      <span className="text-[11px] tracking-wider text-primary/60 font-medium">
        {label}
      </span>
    </div>
  )
}
