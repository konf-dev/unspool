import { create } from 'zustand'
import { supabase, isMockMode } from '@/lib/supabase'

interface AuthStore {
  isAuthenticated: boolean
  isLoading: boolean
  userId: string | null
  token: string | null
  hasCalendar: boolean
  sendOtp: (email: string) => Promise<void>
  verifyOtp: (email: string, code: string) => Promise<void>
  signOut: () => Promise<void>
  _initSession: () => () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  isAuthenticated: false,
  isLoading: true,
  userId: null,
  token: null,
  hasCalendar: false,

  sendOtp: async (email: string) => {
    if (isMockMode || !supabase) return

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { shouldCreateUser: true },
    })
    if (error) throw error
  },

  verifyOtp: async (email: string, code: string) => {
    if (isMockMode) {
      set({ isAuthenticated: true, userId: 'mock-user', token: 'mock-token' })
      return
    }
    if (!supabase) return

    const { error } = await supabase.auth.verifyOtp({
      email,
      token: code,
      type: 'email',
    })
    if (error) throw error
    // onAuthStateChange listener will update the store state
  },

  signOut: async () => {
    if (isMockMode || !supabase) {
      set({ isAuthenticated: false, userId: null, token: null, hasCalendar: false })
      return
    }

    const { error } = await supabase.auth.signOut()
    if (error) throw error
  },

  _initSession: () => {
    if (isMockMode) {
      set({ isLoading: false })
      return () => {}
    }
    if (!supabase) {
      set({ isLoading: false })
      return () => {}
    }

    // Check localStorage first — if no stored session, skip the network call
    // so unauthenticated users see the landing page instantly
    const storageKey = Object.keys(localStorage).find((k) =>
      k.startsWith('sb-') && k.endsWith('-auth-token'),
    )
    if (!storageKey || !localStorage.getItem(storageKey)) {
      set({ isLoading: false })
    }

    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        set({
          isAuthenticated: true,
          userId: session.user.id,
          token: session.access_token,
          hasCalendar: !!session.provider_token,
        })
      }
      set({ isLoading: false })
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session) {
        set({
          isAuthenticated: true,
          userId: session.user.id,
          token: session.access_token,
          hasCalendar: !!session.provider_token,
        })
      } else {
        set({ isAuthenticated: false, userId: null, token: null, hasCalendar: false })
      }
    })

    return () => subscription.unsubscribe()
  },
}))
