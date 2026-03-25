export interface ActionButton {
  label: string
  value: string
}

export interface Message {
  id: string
  role: 'user' | 'reflection'
  content: string
  createdAt: string
  actions?: ActionButton[]
  metadata?: Record<string, unknown>
  status?: 'sending' | 'queued' | 'sent' | 'error'
}

export interface PlateItem {
  id: string
  label: string
  deadline?: string
  hasDeadline: boolean
  isDone: boolean
}

export type SSEEventType = 'token' | 'actions' | 'tool_status' | 'plate' | 'done' | 'error'

export interface ParsedSSEEvent {
  type: SSEEventType | 'unknown'
  content?: string
  tool?: string
  status?: 'running' | 'done'
  items?: Array<{ id: string; content: string; deadline?: string }>
}

export type Route = 'landing' | 'login' | 'chat' | 'privacy' | 'terms'
