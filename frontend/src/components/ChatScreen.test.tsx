import { describe, it, expect, vi, beforeEach } from 'vitest'
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

vi.mock('../lib/api', () => ({
  sendMessage: vi.fn(() => new AbortController()),
  fetchMessages: vi.fn(() => Promise.resolve([])),
  getApiUrl: () => 'http://localhost:8000',
  parseSSEEvent: vi.fn(),
}))

vi.mock('../hooks/useOffline', () => ({
  useOffline: () => ({ isOnline: true }),
}))

vi.mock('../hooks/usePush', () => ({
  usePush: vi.fn(),
}))

vi.mock('../hooks/useCatEasterEgg', () => ({
  useCatEasterEgg: () => ({
    showCat: false,
    variant: 'hopper' as const,
    onCatDone: vi.fn(),
  }),
}))

vi.mock('../hooks/usePWAInstall', () => ({
  usePWAInstall: () => ({
    showPrompt: false,
    isIOS: false,
    triggerInstall: vi.fn(),
    dismiss: vi.fn(),
  }),
}))

import { ChatScreen } from './ChatScreen'
import type { Message } from '../types'

const WELCOME: Message = {
  id: 'welcome',
  role: 'assistant',
  content: 'hey — dump anything on me. tasks, ideas, deadlines, random thoughts. i sort it out.',
  createdAt: new Date().toISOString(),
  actions: [{ label: 'what should I do?', value: 'what should I do?' }],
}

function renderChat(messages: Message[] = [WELCOME]) {
  return render(
    <ChatScreen
      initialMessages={messages}
      token="test-token"
      userId="test-user"
      onSignOut={vi.fn()}
    />,
  )
}

describe('ChatScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorage.clear()
    // Simulate desktop (non-touch) for Enter-to-send behavior
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

  it('renders the welcome message', () => {
    renderChat()
    expect(screen.getByText(/dump anything on me/)).toBeInTheDocument()
  })

  it('renders action buttons from welcome message', () => {
    renderChat()
    expect(screen.getByText('what should I do?')).toBeInTheDocument()
  })

  it('has a text input for sending messages', () => {
    renderChat()
    const textarea = screen.getByPlaceholderText("what's on your mind?")
    expect(textarea).toBeInTheDocument()
  })

  it('shows sign out button', () => {
    renderChat()
    expect(screen.getByText('sign out')).toBeInTheDocument()
  })

  it('sends a message when user types and hits enter on desktop', async () => {
    const { sendMessage } = await import('../lib/api')
    const user = userEvent.setup()

    renderChat()

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    await user.type(textarea, 'hello')
    await user.keyboard('{Enter}')

    expect(sendMessage).toHaveBeenCalledWith(
      'hello',
      expect.any(String),
      'test-token',
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    )
  })

  it('displays multiple messages in order', () => {
    const messages: Message[] = [
      { id: '1', role: 'user', content: 'first message', createdAt: '2026-03-19T10:00:00Z' },
      { id: '2', role: 'assistant', content: 'second message', createdAt: '2026-03-19T10:00:01Z' },
    ]
    renderChat(messages)

    expect(screen.getByText('first message')).toBeInTheDocument()
    expect(screen.getByText('second message')).toBeInTheDocument()
  })

  it('clears draft from localStorage on send', async () => {
    const user = userEvent.setup()
    mockLocalStorage.setItem('unspool-draft', 'saved draft')

    renderChat()

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    await user.type(textarea, 'hello')
    await user.keyboard('{Enter}')

    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('unspool-draft')
  })
})
