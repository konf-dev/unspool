import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement } from 'react'

// Simple render helper — Zustand stores are global singletons,
// no provider wrapping needed.
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, options)
}
