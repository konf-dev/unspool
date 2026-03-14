import { useCallback } from 'react'
import type { ActionButton } from '../types'

interface ActionButtonsProps {
  actions: ActionButton[]
  onAction: (value: string) => void
}

export function ActionButtons({ actions, onAction }: ActionButtonsProps) {
  const handleClick = useCallback(
    (value: string) => {
      navigator.vibrate?.(8)
      onAction(value)
    },
    [onAction],
  )

  return (
    <div className="action-buttons" role="group" aria-label="Suggested actions">
      {actions.map((action) => (
        <button
          key={action.value}
          className="action-btn"
          type="button"
          onClick={() => handleClick(action.value)}
          aria-label={action.label}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}
