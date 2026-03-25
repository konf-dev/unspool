import { useUIStore } from '@/stores/uiStore'

export function useReducedMotion(): boolean {
  return useUIStore((s) => s.prefersReducedMotion)
}
