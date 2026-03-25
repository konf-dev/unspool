import { useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  // #4: Use individual selectors to avoid re-rendering on every store change
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  const userId = useAuthStore((s) => s.userId)
  const token = useAuthStore((s) => s.token)
  const hasCalendar = useAuthStore((s) => s.hasCalendar)

  useEffect(() => {
    const cleanup = useAuthStore.getState()._initSession()
    return cleanup
  }, [])

  return {
    isAuthenticated,
    isLoading,
    userId,
    token,
    hasCalendar,
    sendOtp: useAuthStore.getState().sendOtp,
    verifyOtp: useAuthStore.getState().verifyOtp,
    signOut: useAuthStore.getState().signOut,
  }
}
