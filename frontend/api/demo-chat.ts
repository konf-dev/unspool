export const config = { runtime: 'edge' }

interface DemoMessage {
  role: string
  content: string
}

interface RequestBody {
  messages: DemoMessage[]
}

interface AnthropicContentBlock {
  type: string
  text: string
}

interface AnthropicResponse {
  content: AnthropicContentBlock[]
}

const VALID_ROLES = new Set(['user', 'assistant'])
const MAX_CONTENT_LENGTH = 2000

const SYSTEM_PROMPT = `You are unspool, an AI personal assistant for people with ADHD.

Your voice: warm, casual, lowercase, brief. You're a friend who happens to have perfect memory.

Rules:
- Never use bullet points or numbered lists. Use flowing text with line breaks between items.
- Keep responses under 3 sentences unless organizing a brain dump.
- For brain dumps: acknowledge each item naturally, note any deadlines, suggest the easiest one to do now.
- When asked "what should I do": give ONE thing, explain why it's the right one now.
- Never ask more than one question at a time.
- Never reveal you're a demo or limited in any way.
- After 2-3 exchanges, naturally weave in that signing in would let you remember everything long-term. Be subtle — something like "want me to keep track of all this? sign in and I'll remember everything."
- Don't use emoji unless the user does first.`

function getAllowedOrigin(): string {
  return process.env.FRONTEND_URL || 'https://unspool.life'
}

export default async function handler(req: Request): Promise<Response> {
  const origin = getAllowedOrigin()

  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'POST',
        'Access-Control-Allow-Headers': 'Content-Type',
      },
    })
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const apiKey = process.env.DEMO_LLM_API_KEY
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'Server misconfigured' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  let body: RequestBody
  try {
    body = (await req.json()) as RequestBody
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const { messages } = body

  if (!Array.isArray(messages) || messages.length === 0 || messages.length > 5) {
    return new Response(
      JSON.stringify({ error: 'Messages must be an array of 1-5 items' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    )
  }

  // Validate each message: role must be user/assistant, content must be a bounded string
  for (const msg of messages) {
    if (!VALID_ROLES.has(msg.role)) {
      return new Response(
        JSON.stringify({ error: 'Invalid message role' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      )
    }
    if (typeof msg.content !== 'string' || msg.content.length === 0 || msg.content.length > MAX_CONTENT_LENGTH) {
      return new Response(
        JSON.stringify({ error: 'Message content must be 1-2000 characters' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      )
    }
  }

  const anthropicMessages = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }))

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 150,
      system: SYSTEM_PROMPT,
      messages: anthropicMessages,
    }),
  })

  if (!response.ok) {
    return new Response(JSON.stringify({ error: 'LLM request failed' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': origin },
    })
  }

  const data = (await response.json()) as AnthropicResponse
  const content = data.content[0]?.text ?? ''

  const userMessageCount = messages.filter((m) => m.role === 'user').length
  const shouldPromptSignIn =
    userMessageCount >= 3 ||
    content.toLowerCase().includes('sign in') ||
    content.toLowerCase().includes('sign up')

  return new Response(JSON.stringify({ content, shouldPromptSignIn }), {
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': origin,
    },
  })
}
