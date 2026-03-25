import { useOffline } from '@/hooks/useOffline'

export function OfflineBanner() {
  const { isOnline } = useOffline()

  if (isOnline) return null

  return (
    <div
      className="fixed left-0 right-0 z-[60] flex justify-center pointer-events-none"
      style={{ top: 'calc(3rem + env(safe-area-inset-top, 0px))' }}
    >
      <div className="bg-surface-container-high text-on-surface-variant text-xs tracking-wider px-4 py-2 rounded-full">
        offline — messages will send when you reconnect
      </div>
    </div>
  )
}
