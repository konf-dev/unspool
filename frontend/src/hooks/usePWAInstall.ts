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
  const [isDismissed, setIsDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === 'true')
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

  // Track user interactions (new messages sent, not total count)
  useEffect(() => {
    if (messageCount > prevMessageCountRef.current) {
      const newInteractions = messageCount - prevMessageCountRef.current
      prevMessageCountRef.current = messageCount
      const current = parseInt(localStorage.getItem(INTERACTION_KEY) ?? '0', 10)
      localStorage.setItem(INTERACTION_KEY, String(current + newInteractions))
    }
  }, [messageCount])

  const interactionCount = parseInt(localStorage.getItem(INTERACTION_KEY) ?? '0', 10)
  const showPrompt = (canPrompt || isIOS) && interactionCount >= 3 && !isDismissed

  const triggerInstall = useCallback(async () => {
    const prompt = deferredPromptRef.current
    if (!prompt) return
    await prompt.prompt()
    await prompt.userChoice
    deferredPromptRef.current = null
  }, [])

  const dismiss = useCallback(() => {
    localStorage.setItem(DISMISS_KEY, 'true')
    setIsDismissed(true)
  }, [])

  return { showPrompt, isIOS, triggerInstall, dismiss }
}
