import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../lib/supabase', () => ({
  supabase: null,
  isMockMode: true,
}))

vi.mock('../lib/api', () => ({
  getApiUrl: () => 'http://localhost:8000',
}))

import { useAuth } from './useAuth'

describe('useAuth (mock mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts unauthenticated and not loading in mock mode', () => {
    const { result } = renderHook(() => useAuth())

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.userId).toBeNull()
    expect(result.current.token).toBeNull()
  })

  it('signs in with Google in mock mode', async () => {
    const { result } = renderHook(() => useAuth())

    await act(async () => {
      await result.current.signInWithGoogle()
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.userId).toBe('mock-user')
    expect(result.current.token).toBe('mock-token')
  })

  it('signs out in mock mode', async () => {
    const { result } = renderHook(() => useAuth())

    await act(async () => {
      await result.current.signInWithGoogle()
    })

    expect(result.current.isAuthenticated).toBe(true)

    await act(async () => {
      await result.current.signOut()
    })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.userId).toBeNull()
    expect(result.current.token).toBeNull()
  })
})
