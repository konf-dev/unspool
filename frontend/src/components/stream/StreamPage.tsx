import { useCallback } from 'react'
import { useChat } from '@/hooks/useChat'
import { usePush } from '@/hooks/usePush'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import { usePlateStore } from '@/stores/plateStore'
import { DragHandle } from '@/components/shared/DragHandle'
import { AmbientGlow } from '@/components/shared/AmbientGlow'
import { OfflineBanner } from '@/components/system/OfflineBanner'
import { PWAInstallPrompt } from '@/components/system/PWAInstallPrompt'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { PlateOverlay } from '@/components/plate/PlateOverlay'

export function StreamPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useUIStore((s) => s.navigate)

  const handleSignOut = useCallback(async () => {
    await useAuthStore.getState().signOut()
    navigate('login')
  }, [navigate])
  const {
    messages,
    streamingContent,
    isStreaming,
    isThinking,
    toolStatus,
    send,
    stop,
    onAction,
  } = useChat()
  const plateIsOpen = usePlateStore((s) => s.isOpen)

  // Push notifications after 6+ messages
  usePush(token ?? '', messages.filter((m) => m.role === 'user').length)

  return (
    <div className="fixed inset-0 flex flex-col bg-background overflow-hidden">
      <AmbientGlow />
      <DragHandle />
      <OfflineBanner />
      <PlateOverlay />

      <button
        type="button"
        onClick={() => void handleSignOut()}
        className="fixed right-4 z-[60] text-xs text-on-surface-variant/50 hover:text-on-surface-variant/60 transition-colors tracking-wide"
        style={{ top: 'calc(1rem + env(safe-area-inset-top, 0px))' }}
      >
        sign out
      </button>

      <main
        className={`flex-1 flex flex-col overflow-hidden transition-all duration-300 ${
          plateIsOpen ? 'opacity-30 blur-sm scale-[0.98]' : ''
        }`}
      >
        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          isThinking={isThinking}
          toolStatus={toolStatus}
          onAction={onAction}
        />

        <InputBar
          onSend={send}
          onStop={stop}
          isStreaming={isStreaming}
          disabled={plateIsOpen}
        />
      </main>

      <PWAInstallPrompt messageCount={messages.filter((m) => m.role === 'user').length} />
    </div>
  )
}
