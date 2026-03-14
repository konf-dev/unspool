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
  content: "hey, i'm unspool.",
  createdAt: new Date().toISOString(),
  actions: [{ label: 'suggest something', value: 'what should I do?' }],
}

describe('ChatScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorage.clear()
  })

  it('renders the welcome message', () => {
    render(
      <ChatScreen
        initialMessages={[WELCOME]}
        token="test-token"
        userId="test-user"
        onSignOut={vi.fn()}
      />,
    )

    expect(screen.getByText("hey, i'm unspool.")).toBeInTheDocument()
  })

  it('renders action buttons from welcome message', () => {
    render(
      <ChatScreen
        initialMessages={[WELCOME]}
        token="test-token"
        userId="test-user"
        onSignOut={vi.fn()}
      />,
    )

    expect(screen.getByText('suggest something')).toBeInTheDocument()
  })

  it('has a text input for sending messages', () => {
    render(
      <ChatScreen
        initialMessages={[WELCOME]}
        token="test-token"
        userId="test-user"
        onSignOut={vi.fn()}
      />,
    )

    const textarea = screen.getByPlaceholderText("what's on your mind?")
    expect(textarea).toBeInTheDocument()
  })

  it('shows sign out button', () => {
    render(
      <ChatScreen
        initialMessages={[WELCOME]}
        token="test-token"
        userId="test-user"
        onSignOut={vi.fn()}
      />,
    )

    expect(screen.getByText('sign out')).toBeInTheDocument()
  })

  it('sends a message when user types and hits enter', async () => {
    const { sendMessage } = await import('../lib/api')
    const user = userEvent.setup()

    render(
      <ChatScreen
        initialMessages={[WELCOME]}
        token="test-token"
        userId="test-user"
        onSignOut={vi.fn()}
      />,
    )

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
})
