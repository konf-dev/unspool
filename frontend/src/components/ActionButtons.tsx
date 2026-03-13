import type { ActionButton } from '../types'

interface ActionButtonsProps {
  actions: ActionButton[]
  onAction: (value: string) => void
}

export function ActionButtons({ actions, onAction }: ActionButtonsProps) {
  return (
    <div className="action-buttons" role="group" aria-label="Suggested actions">
      {actions.map((action) => (
        <button
          key={action.value}
          className="action-btn"
          type="button"
          onClick={() => onAction(action.value)}
          aria-label={action.label}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}
