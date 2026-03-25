import type { ActionButton } from '@/types'

interface ActionChipsProps {
  actions: ActionButton[]
  onAction: (action: ActionButton) => void
}

export function ActionChips({ actions, onAction }: ActionChipsProps) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {actions.map((action, i) => (
        <button
          key={`${action.value}-${i}`}
          onClick={() => onAction(action)}
          className="px-4 py-1.5 rounded-full text-sm text-primary font-light tracking-wide ghost-border hover:bg-surface-container-high active:scale-[0.97] transition-all duration-300 animate-fade-in"
          style={{ animationDelay: `${i * 80}ms` }}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}
