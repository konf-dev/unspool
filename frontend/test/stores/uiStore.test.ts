import { describe, it, expect, beforeEach } from 'vitest'
import { useUIStore } from '@/stores/uiStore'

describe('uiStore', () => {
  beforeEach(() => {
    useUIStore.setState({
      route: 'landing',
      isOnline: true,
      prefersReducedMotion: false,
    })
  })

  it('navigates to a route', () => {
    useUIStore.getState().navigate('chat')
    expect(useUIStore.getState().route).toBe('chat')
  })

  it('sets online state', () => {
    useUIStore.getState().setOnline(false)
    expect(useUIStore.getState().isOnline).toBe(false)
  })

  it('initializes with landing route', () => {
    expect(useUIStore.getState().route).toBe('landing')
  })
})
