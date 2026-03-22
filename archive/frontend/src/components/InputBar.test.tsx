import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const store: Record<string, string> = {}
const mockLocalStorage = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    store[key] = value
  }),
  removeItem: vi.fn((key: string) => {
    delete store[key]
  }),
  clear: vi.fn(() => {
    Object.keys(store).forEach((k) => delete store[k])
  }),
  get length() {
    return Object.keys(store).length
  },
  key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
}
Object.defineProperty(globalThis, 'localStorage', { value: mockLocalStorage, writable: true })

vi.mock('../hooks/useVoice', () => ({
  useVoice: () => ({
    isRecording: false,
    isSupported: false,
    transcript: '',
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    clearTranscript: vi.fn(),
  }),
}))

import { InputBar } from './InputBar'

function renderInputBar(props: Partial<{ onSend: (msg: string) => void; isStreaming: boolean; onStop: () => void }> = {}) {
  const defaultProps = {
    onSend: vi.fn(),
    isStreaming: false,
    onStop: vi.fn(),
  }
  return render(<InputBar {...defaultProps} {...props} />)
}

describe('InputBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockLocalStorage.clear()
    // Desktop by default
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn((query: string) => ({
        matches: query === '(pointer: coarse)' ? false : false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
      writable: true,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the textarea with placeholder', () => {
    renderInputBar()
    expect(screen.getByPlaceholderText("what's on your mind?")).toBeInTheDocument()
  })

  it('restores draft from localStorage on mount', () => {
    store['unspool-draft'] = 'my saved draft'
    renderInputBar()
    const textarea = screen.getByPlaceholderText("what's on your mind?") as HTMLTextAreaElement
    expect(textarea.value).toBe('my saved draft')
  })

  it('saves draft to localStorage after 500ms debounce', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    renderInputBar()

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    await user.type(textarea, 'draft text')

    // Wait for debounce
    await new Promise((r) => setTimeout(r, 600))

    expect(mockLocalStorage.setItem).toHaveBeenCalledWith('unspool-draft', 'draft text')
  })

  it('clears draft on send', async () => {
    vi.useRealTimers()
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderInputBar({ onSend })

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    await user.type(textarea, 'sending this')
    await user.keyboard('{Enter}')

    expect(onSend).toHaveBeenCalledWith('sending this')
    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('unspool-draft')
  })

  it('removes draft key when input is cleared', async () => {
    vi.useRealTimers()
    store['unspool-draft'] = 'old draft'
    const user = userEvent.setup()
    renderInputBar()

    const textarea = screen.getByPlaceholderText("what's on your mind?") as HTMLTextAreaElement
    await user.clear(textarea)

    await new Promise((r) => setTimeout(r, 600))
    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('unspool-draft')
  })

  it('does not send empty messages', async () => {
    vi.useRealTimers()
    const onSend = vi.fn()
    const user = userEvent.setup()
    renderInputBar({ onSend })

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    await user.click(textarea)
    await user.keyboard('{Enter}')

    expect(onSend).not.toHaveBeenCalled()
  })
})
