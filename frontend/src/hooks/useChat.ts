import { useEffect, useRef, useCallback } from 'react'
import { useMessageStore } from '@/stores/messageStore'
import { useAuthStore } from '@/stores/authStore'

export function useChat() {
  const token = useAuthStore((s) => s.token)
  const messages = useMessageStore((s) => s.messages)
  const streamingContent = useMessageStore((s) => s.streamingContent)
  const isStreaming = useMessageStore((s) => s.isStreaming)
  const isThinking = useMessageStore((s) => s.isThinking)
  const toolStatus = useMessageStore((s) => s.toolStatus)
  const pendingActions = useMessageStore((s) => s.pendingActions)
  const hasMore = useMessageStore((s) => s.hasMore)

  const historyFetchedRef = useRef(false)

  // Fetch message history once on mount when token is available
  useEffect(() => {
    if (token && !historyFetchedRef.current) {
      historyFetchedRef.current = true
      void useMessageStore.getState().fetchHistory(token)
    }
  }, [token])

  // Reset fetch flag on sign-out
  useEffect(() => {
    if (!token) historyFetchedRef.current = false
  }, [token])

  // Flush offline queue when coming online
  useEffect(() => {
    if (token && navigator.onLine) {
      useMessageStore.getState().flushQueue(token)
    }
  }, [token])

  const send = useCallback(
    (content: string) => {
      if (!token || !content.trim()) return
      useMessageStore.getState().sendMessage(content.trim(), token)
    },
    [token],
  )

  const onAction = useCallback(
    (action: { label: string; value: string }) => {
      if (!token) return
      useMessageStore.getState().handleAction(action, token)
    },
    [token],
  )

  const stop = useCallback(() => {
    useMessageStore.getState().stopStreaming()
  }, [])

  const loadMore = useCallback(() => {
    if (!token || !hasMore) return
    const oldest = useMessageStore.getState().messages[0]
    if (oldest) {
      void useMessageStore.getState().fetchHistory(token, oldest.id)
    }
  }, [token, hasMore])

  return {
    messages,
    streamingContent,
    isStreaming,
    isThinking,
    toolStatus,
    pendingActions,
    hasMore,
    send,
    stop,
    onAction,
    loadMore,
  }
}
