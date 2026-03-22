import { useState, useEffect, useCallback } from 'react'
import { supabase, isMockMode } from '../lib/supabase'
import { getApiUrl } from '../lib/api'

interface UseAuthReturn {
  isAuthenticated: boolean
  isLoading: boolean
  userId: string | null
  token: string | null
  hasCalendar: boolean
  signInWithGoogle: () => Promise<void>
  signInWithEmail: (email: string) => Promise<void>
  signOut: () => Promise<void>
}

export function useAuth(): UseAuthReturn {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [userId, setUserId] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [hasCalendar, setHasCalendar] = useState(false)

  useEffect(() => {
    if (isMockMode) {
      setIsLoading(false)
      return
    }

    if (!supabase) return

    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setIsAuthenticated(true)
        setUserId(session.user.id)
        setToken(session.access_token)
        setHasCalendar(!!session.provider_token)
      }
      setIsLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (session) {
        setIsAuthenticated(true)
        setUserId(session.user.id)
        setToken(session.access_token)
        setHasCalendar(!!session.provider_token)

        if (
          event === 'SIGNED_IN' &&
          session.provider_refresh_token
        ) {
          await storeCalendarToken(session.provider_refresh_token, session.access_token)
        }
      } else if (event === 'TOKEN_REFRESHED' && !session) {
        // Token refresh failed — force sign-out
        setIsAuthenticated(false)
        setUserId(null)
        setToken(null)
        setHasCalendar(false)
      } else {
        setIsAuthenticated(false)
        setUserId(null)
        setToken(null)
        setHasCalendar(false)
      }
    })

    return () => subscription.unsubscribe()
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (isMockMode) {
      setIsAuthenticated(true)
      setUserId('mock-user')
      setToken('mock-token')
      return
    }
    if (!supabase) return

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin,
        scopes: 'https://www.googleapis.com/auth/calendar.readonly',
        queryParams: {
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    })

    if (error) throw error
  }, [])

  const signInWithEmail = useCallback(async (email: string) => {
    if (isMockMode || !supabase) return

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: window.location.origin,
      },
    })

    if (error) throw error
  }, [])

  const signOut = useCallback(async () => {
    if (isMockMode || !supabase) {
      setIsAuthenticated(false)
      setUserId(null)
      setToken(null)
      return
    }

    const { error } = await supabase.auth.signOut()
    if (error) throw error
  }, [])

  return {
    isAuthenticated,
    isLoading,
    userId,
    token,
    hasCalendar,
    signInWithGoogle,
    signInWithEmail,
    signOut,
  }
}

async function storeCalendarToken(
  refreshToken: string,
  accessToken: string,
): Promise<void> {
  try {
    await fetch(`${getApiUrl()}/api/auth/store-token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ provider_refresh_token: refreshToken }),
    })
  } catch {
    // Non-critical — calendar sync will just be unavailable
  }
}
