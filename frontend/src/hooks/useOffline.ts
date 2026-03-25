import { useUIStore } from '@/stores/uiStore'

export function useOffline() {
  return { isOnline: useUIStore((s) => s.isOnline) }
}
