import type { PlateItem as PlateItemType } from '@/types'

interface PlateItemProps {
  item: PlateItemType
}

export function PlateItem({ item }: PlateItemProps) {
  return (
    <div className="flex items-center justify-between group" role="listitem">
      <div className="flex items-center space-x-4">
        <div
          className={`w-2 h-2 rounded-full ${
            item.hasDeadline
              ? 'bg-tertiary shadow-[0_0_8px_rgba(255,231,202,0.4)]'
              : 'bg-primary shadow-[0_0_8px_rgba(174,205,192,0.4)]'
          }`}
        />
        <span
          className={`font-light text-sm tracking-wide ${
            item.isDone ? 'text-on-surface-variant/40 line-through' : 'text-on-surface-variant'
          }`}
        >
          {item.label}
        </span>
      </div>
      {item.deadline && (
        <span className="text-[11px] font-medium tracking-[0.05em] text-outline uppercase">
          {item.deadline}
        </span>
      )}
    </div>
  )
}
