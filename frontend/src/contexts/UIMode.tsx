import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import type { UIMode } from '../types'

const STORAGE_KEY = 'unspool-ui-mode'
const DEFAULT_MODE: UIMode = 'thought'

interface UIModeContextValue {
  uiMode: UIMode
  setUIMode: (mode: UIMode) => void
}

const UIModeContext = createContext<UIModeContextValue>({
  uiMode: DEFAULT_MODE,
  setUIMode: () => {},
})

export function UIModeProvider({ children }: { children: ReactNode }) {
  const [uiMode, setUIModeState] = useState<UIMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'chat' || stored === 'thought') return stored
    return DEFAULT_MODE
  })

  const setUIMode = useCallback((mode: UIMode) => {
    setUIModeState(mode)
    localStorage.setItem(STORAGE_KEY, mode)
  }, [])

  return (
    <UIModeContext.Provider value={{ uiMode, setUIMode }}>
      {children}
    </UIModeContext.Provider>
  )
}

export function useUIMode(): UIModeContextValue {
  return useContext(UIModeContext)
}
