import { useState, useCallback, useRef, useEffect } from 'react'
import { COMPLETION_KEYWORDS } from '../lib/constants'

type CatVariant = 'hopper' | 'observer' | 'peek'

interface UseCatEasterEggReturn {
  showCat: boolean
  variant: CatVariant
  onCatDone: () => void
}
const MIN_INTERVAL_MS = 5 * 60 * 1000
const IDLE_TIMEOUT_MS = 30 * 1000

function pickVariant(): CatVariant {
  const variants: CatVariant[] = ['hopper', 'observer', 'peek']
  const index = Math.floor(Math.random() * variants.length)
  return variants[index] ?? 'hopper'
}

function isCompletionMessage(content: string): boolean {
  const lower = content.toLowerCase()
  return COMPLETION_KEYWORDS.some((kw) => lower.includes(kw))
}

export function useCatEasterEgg(
  messageCount: number,
  isStreaming: boolean,
  isThinking: boolean,
  lastAssistantContent: string | null,
): UseCatEasterEggReturn {
  const [showCat, setShowCat] = useState(false)
  const [variant, setVariant] = useState<CatVariant>('hopper')
  const lastAppearanceRef = useRef<number>(0)
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const idleShownRef = useRef(false)
  const prevMessageCountRef = useRef(messageCount)

  const canAppear = useCallback(() => {
    if (messageCount < 6) return false
    if (isStreaming || isThinking) return false
    if (showCat) return false
    if (Date.now() - lastAppearanceRef.current < MIN_INTERVAL_MS) return false
    return true
  }, [messageCount, isStreaming, isThinking, showCat])

  const triggerCat = useCallback(() => {
    setVariant(pickVariant())
    setShowCat(true)
    lastAppearanceRef.current = Date.now()
  }, [])

  const onCatDone = useCallback(() => {
    setShowCat(false)
    idleShownRef.current = false
  }, [])

  useEffect(() => {
    if (!lastAssistantContent) return
    if (!canAppear()) return
    if (messageCount <= prevMessageCountRef.current) return

    prevMessageCountRef.current = messageCount

    if (isCompletionMessage(lastAssistantContent) && Math.random() < 0.05) {
      triggerCat()
    }
  }, [lastAssistantContent, messageCount, canAppear, triggerCat])

  useEffect(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current)
      idleTimerRef.current = null
    }

    if (idleShownRef.current) return

    idleTimerRef.current = setTimeout(() => {
      if (canAppear()) {
        idleShownRef.current = true
        triggerCat()
      }
    }, IDLE_TIMEOUT_MS)

    return () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current)
      }
    }
  }, [messageCount, canAppear, triggerCat])

  return { showCat, variant, onCatDone }
}
