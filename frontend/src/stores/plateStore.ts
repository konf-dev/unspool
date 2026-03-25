import { create } from 'zustand'
import type { PlateItem } from '@/types'

interface PlateStore {
  summary: string
  items: PlateItem[]
  isOpen: boolean
  setOpen: (open: boolean) => void
  setPlate: (items: PlateItem[]) => void
  updateFromMessages: (messages: Array<{ role: string; content: string; metadata?: Record<string, unknown> }>) => void
}

export const usePlateStore = create<PlateStore>((set) => ({
  summary: '',
  items: [],
  isOpen: false,

  setOpen: (open: boolean) => set({ isOpen: open }),

  setPlate: (items: PlateItem[]) => set({ items }),

  updateFromMessages: (messages) => {
    // Extract plate data from assistant messages that contain graph context
    // The backend provides plate items via message metadata
    const lastReflection = [...messages]
      .reverse()
      .find((m) => m.role === 'reflection' || m.role === 'assistant')

    if (lastReflection?.metadata?.plate) {
      const plate = lastReflection.metadata.plate as {
        summary?: string
        items?: Array<{ id: string; content: string; deadline?: string }>
      }
      set({
        summary: plate.summary ?? '',
        items: (plate.items ?? []).map((p) => ({
          id: p.id,
          label: p.content,
          deadline: p.deadline,
          hasDeadline: !!p.deadline,
          isDone: false,
        })),
      })
    }
  },
}))
