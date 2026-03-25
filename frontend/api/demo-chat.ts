export const config = { runtime: 'edge' }

interface DemoMessage {
  role: string
  content: string
}

interface RequestBody {
  messages: DemoMessage[]
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

function getAllowedOrigins(): string[] {
  const origins = [process.env.FRONTEND_URL || 'https://unspool.life']
  if (process.env.CORS_EXTRA_ORIGINS) {
    origins.push(...process.env.CORS_EXTRA_ORIGINS.split(','))
  }
  return origins
}

function getCorsOrigin(req: Request): string {
  const requestOrigin = req.headers.get('origin') ?? ''
  const allowed = getAllowedOrigins()
  if (allowed.includes(requestOrigin)) return requestOrigin
  return allowed[0] ?? ''
}

export default async function handler(req: Request): Promise<Response> {
  const origin = getCorsOrigin(req)

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

  const apiKey = process.env.GOOGLE_API_KEY
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

  if (!Array.isArray(messages) || messages.length === 0 || messages.length > 10) {
    return new Response(
      JSON.stringify({ error: 'Messages must be an array of 1-10 items' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    )
  }

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

  const chatMessages = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }))

  // Use Gemini Flash via OpenAI-compatible endpoint (cheapest option)
  const baseUrl = process.env.DEMO_LLM_BASE_URL || 'https://generativelanguage.googleapis.com/v1beta/openai'
  const model = process.env.DEMO_LLM_MODEL || 'gemini-2.0-flash-lite'

  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      max_tokens: 150,
      messages: [{ role: 'system', content: SYSTEM_PROMPT }, ...chatMessages],
    }),
  })

  if (!response.ok) {
    return new Response(JSON.stringify({ error: 'LLM request failed' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': origin },
    })
  }

  const data = (await response.json()) as { choices: Array<{ message: { content: string } }> }
  const content = data.choices[0]?.message?.content ?? ''

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
