import { useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  const store = useAuthStore()

  useEffect(() => {
    const cleanup = store._initSession()
    return cleanup
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    isAuthenticated: store.isAuthenticated,
    isLoading: store.isLoading,
    userId: store.userId,
    token: store.token,
    hasCalendar: store.hasCalendar,
    sendOtp: store.sendOtp,
    verifyOtp: store.verifyOtp,
    signOut: store.signOut,
  }
}
