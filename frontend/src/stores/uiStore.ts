import { create } from 'zustand'
import type { Route } from '@/types'

const ROUTE_MAP: Record<string, Route> = {
  '/': 'landing',
  '/login': 'login',
  '/chat': 'chat',
  '/privacy': 'privacy',
  '/terms': 'terms',
}

const PATH_MAP: Record<Route, string> = {
  landing: '/',
  login: '/login',
  chat: '/chat',
  privacy: '/privacy',
  terms: '/terms',
}

function getRouteFromPath(): Route {
  const path = window.location.pathname
  return ROUTE_MAP[path] ?? 'landing'
}

interface UIStore {
  route: Route
  isOnline: boolean
  prefersReducedMotion: boolean
  navigate: (route: Route) => void
  setOnline: (online: boolean) => void
  _initRoute: () => () => void
}

export const useUIStore = create<UIStore>((set) => ({
  route: getRouteFromPath(),
  isOnline: navigator.onLine,
  prefersReducedMotion:
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,

  navigate: (route: Route) => {
    const path = PATH_MAP[route]
    window.history.pushState({}, '', path)
    set({ route })
  },

  setOnline: (online: boolean) => set({ isOnline: online }),

  _initRoute: () => {
    const handlePopState = () => {
      set({ route: getRouteFromPath() })
    }
    window.addEventListener('popstate', handlePopState)

    const handleOnline = () => set({ isOnline: true })
    const handleOffline = () => set({ isOnline: false })
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handleMotion = (e: MediaQueryListEvent) =>
      set({ prefersReducedMotion: e.matches })
    mq.addEventListener('change', handleMotion)

    return () => {
      window.removeEventListener('popstate', handlePopState)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      mq.removeEventListener('change', handleMotion)
    }
  },
}))
