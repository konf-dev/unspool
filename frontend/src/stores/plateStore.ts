import { create } from 'zustand'
import type { PlateItem } from '@/types'

interface PlateStore {
  summary: string
  items: PlateItem[]
  isOpen: boolean
  setOpen: (open: boolean) => void
  setPlate: (items: PlateItem[]) => void
}

export const usePlateStore = create<PlateStore>((set) => ({
  summary: '',
  items: [],
  isOpen: false,

  setOpen: (open: boolean) => set({ isOpen: open }),

  setPlate: (items: PlateItem[]) => set({ items }),
}))
