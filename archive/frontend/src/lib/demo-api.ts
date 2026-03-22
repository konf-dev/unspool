interface DemoMessage {
  role: 'user' | 'assistant'
  content: string
}

interface DemoResponse {
  content: string
  shouldPromptSignIn: boolean
}

const DEMO_COUNT_KEY = 'unspool-demo-count'
const MAX_DEMO_MESSAGES = 5

export async function sendDemoMessage(messages: DemoMessage[]): Promise<DemoResponse> {
  const count = getDemoMessageCount()

  if (count >= MAX_DEMO_MESSAGES) {
    return {
      content:
        "i'd love to keep chatting — sign in and i'll remember everything we've talked about.",
      shouldPromptSignIn: true,
    }
  }

  const response = await fetch('/api/demo-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })

  if (!response.ok) {
    throw new Error('Demo chat request failed')
  }

  const result = (await response.json()) as DemoResponse

  // Increment only after successful response so failures don't waste attempts
  localStorage.setItem(DEMO_COUNT_KEY, String(count + 1))

  return result
}

export function getDemoMessageCount(): number {
  return parseInt(localStorage.getItem(DEMO_COUNT_KEY) ?? '0', 10)
}
