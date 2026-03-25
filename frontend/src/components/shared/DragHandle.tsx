import { usePlateStore } from '@/stores/plateStore'

export function DragHandle() {
  const setOpen = usePlateStore((s) => s.setOpen)

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 flex justify-center items-start h-12 cursor-grab active:cursor-grabbing"
      onPointerDown={() => setOpen(true)}
    >
      <div className="w-10 h-1 mt-4 rounded-full bg-surface-container-high" />
    </div>
  )
}
