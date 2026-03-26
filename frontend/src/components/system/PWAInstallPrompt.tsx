import { usePWAInstall } from '@/hooks/usePWAInstall'

export function PWAInstallPrompt({ messageCount }: { messageCount: number }) {
  const { showPrompt, isIOS, triggerInstall, dismiss } = usePWAInstall(messageCount)

  if (!showPrompt) return null

  return (
    <div className="fixed bottom-24 left-4 right-4 z-40 flex justify-center animate-fade-in">
      <div className="bg-surface-container-high rounded-2xl p-4 max-w-sm w-full shadow-[0_20px_40px_rgba(0,0,0,0.4)]">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-on-surface text-sm font-medium">add unspool to home screen</p>
            <p className="text-on-surface-variant text-xs">
              {isIOS
                ? 'tap share, then "add to home screen"'
                : 'for quick access and offline support'}
            </p>
          </div>
          <button
            onClick={dismiss}
            className="text-on-surface-variant/60 hover:text-on-surface-variant text-lg leading-none"
            aria-label="Dismiss install prompt"
          >
            &times;
          </button>
        </div>
        {!isIOS && (
          <button
            onClick={() => void triggerInstall()}
            className="mt-3 w-full bg-primary text-on-primary rounded-full py-2 text-sm font-medium tracking-wide hover:bg-primary-dim transition-colors duration-300"
          >
            install
          </button>
        )}
      </div>
    </div>
  )
}
