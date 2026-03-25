import { useRef, useEffect, useCallback, useState } from 'react'

interface UseScrollAnchorReturn {
  scrollRef: React.RefObject<HTMLDivElement | null>
  isAtBottom: boolean
  scrollToBottom: () => void
}

export function useScrollAnchor(deps: unknown[]): UseScrollAnchorReturn {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const userScrolledRef = useRef(false)

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    userScrolledRef.current = false
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const handleScroll = () => {
      const threshold = 100
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
      setIsAtBottom(atBottom)
      if (!atBottom) {
        userScrolledRef.current = true
      }
    }

    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  // Auto-scroll when new content arrives and user hasn't scrolled up
  useEffect(() => {
    if (!userScrolledRef.current) {
      const el = scrollRef.current
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { scrollRef, isAtBottom, scrollToBottom }
}
