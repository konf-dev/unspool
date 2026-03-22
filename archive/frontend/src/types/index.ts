export type UIMode = 'chat' | 'thought'

export type MessageRole = 'user' | 'assistant'

export interface ActionButton {
  label: string
  value: string
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  createdAt: string
  actions?: ActionButton[]
  metadata?: Record<string, unknown>
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  userId: string | null
  hasCalendar: boolean
}

export interface ChatState {
  messages: Message[]
  streamingContent: string | null
  isStreaming: boolean
  isThinking: boolean
  pendingActions: ActionButton[] | null
}

export type SSEEventType = 'token' | 'actions' | 'tool_status' | 'done' | 'error'

export interface SSEEvent {
  type: SSEEventType
  data: string | ActionButton[] | null
}
