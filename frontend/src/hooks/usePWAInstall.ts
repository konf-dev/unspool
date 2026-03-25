import { useState, useEffect, useRef, useCallback } from 'react'

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

interface UsePWAInstallReturn {
  showPrompt: boolean
  isIOS: boolean
  triggerInstall: () => Promise<void>
  dismiss: () => void
}

const DISMISS_KEY = 'unspool-pwa-dismissed'
const INTERACTION_KEY = 'unspool-pwa-interactions'

function detectIOS(): boolean {
  return /iPhone|iPad/.test(navigator.userAgent) && !navigator.userAgent.includes('CriOS')
}

export function usePWAInstall(messageCount: number): UsePWAInstallReturn {
  const deferredPromptRef = useRef<BeforeInstallPromptEvent | null>(null)
  const [canPrompt, setCanPrompt] = useState(false)
  const [isDismissed, setIsDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === 'true' } catch { return false }
  })
  const isIOS = useRef(detectIOS()).current
  const prevMessageCountRef = useRef(messageCount)

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      deferredPromptRef.current = e as BeforeInstallPromptEvent
      setCanPrompt(true)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  // #10: Track interaction count in state instead of reading localStorage every render
  const [interactionCount, setInteractionCount] = useState(() => {
    try { return parseInt(localStorage.getItem(INTERACTION_KEY) ?? '0', 10) } catch { return 0 }
  })
  useEffect(() => {
    if (messageCount > prevMessageCountRef.current) {
      const newInteractions = messageCount - prevMessageCountRef.current
      prevMessageCountRef.current = messageCount
      const updated = interactionCount + newInteractions
      setInteractionCount(updated)
      try { localStorage.setItem(INTERACTION_KEY, String(updated)) } catch { /* ignore */ }
    }
  }, [messageCount, interactionCount])

  const showPrompt = (canPrompt || isIOS) && interactionCount >= 3 && !isDismissed

  const triggerInstall = useCallback(async () => {
    const prompt = deferredPromptRef.current
    if (!prompt) return
    await prompt.prompt()
    await prompt.userChoice
    deferredPromptRef.current = null
  }, [])

  const dismiss = useCallback(() => {
    try { localStorage.setItem(DISMISS_KEY, 'true') } catch { /* ignore */ }
    setIsDismissed(true)
  }, [])

  return { showPrompt, isIOS, triggerInstall, dismiss }
}
