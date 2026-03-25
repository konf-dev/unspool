import { usePlateStore } from '@/stores/plateStore'

export function DragHandle() {
  const { isOpen, setOpen } = usePlateStore()

  return (
    <div
      className="fixed left-0 right-0 z-50 flex justify-center items-start h-12 pointer-events-none"
      style={{ top: 'env(safe-area-inset-top, 0px)' }}
    >
      {/* #8/#9: Only the handle bar itself receives pointer events, not the full-width area */}
      <button
        type="button"
        className="w-10 h-1 mt-4 rounded-full bg-surface-container-high pointer-events-auto cursor-grab active:cursor-grabbing"
        onClick={() => setOpen(!isOpen)}
        aria-label={isOpen ? 'Close plate' : 'Open plate'}
        aria-expanded={isOpen}
      />
    </div>
  )
}
