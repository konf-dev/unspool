import type { ActionButton, Message } from '../types'

const MOCK_RESPONSES: Array<{
  patterns: RegExp[]
  response: string
  actions?: ActionButton[]
}> = [
  {
    patterns: [/grocer/i, /shop/i, /buy/i, /pick up/i],
    response:
      "got it — i'll remember the groceries. whenever you're ready to head out, just ask me what's up and i'll surface it.",
    actions: [{ label: "what's next?", value: 'what should I do next?' }],
  },
  {
    patterns: [/what should/i, /what do i/i, /what.?s next/i, /next thing/i],
    response:
      "you mentioned needing to call the dentist — it's been on your mind for a few days and it's a quick one. want to knock it out?",
    actions: [
      { label: 'done with that', value: "i'm done with calling the dentist" },
      { label: 'skip for now', value: "skip that, what else?" },
    ],
  },
  {
    patterns: [/done/i, /finished/i, /did it/i, /completed/i],
    response: "nice, checked that off. you're in a good flow — want another one or taking a break?",
    actions: [{ label: "what's next?", value: 'what should I do next?' }],
  },
  {
    patterns: [/stress/i, /overwhelm/i, /anxious/i, /can.?t focus/i, /too much/i],
    response:
      "i hear you. you don't need to figure it all out right now. everything's saved — nothing's going to slip through. want to just pick one small thing to do, or take a breather?",
    actions: [
      { label: 'one small thing', value: 'give me something easy to do' },
      { label: 'taking a break', value: "i'm going to take a break" },
    ],
  },
  {
    patterns: [/remind/i, /don.?t forget/i, /remember/i],
    response: "locked in. i'll bring it up when the time feels right.",
  },
  {
    patterns: [/break/i, /rest/i, /later/i, /not now/i],
    response: "sounds good. everything's here when you get back. no rush.",
  },
  {
    patterns: [/hello/i, /hi\b/i, /hey/i, /morning/i, /afternoon/i],
    response:
      "hey! you've got a few things floating around but nothing urgent. want me to suggest something, or just dumping thoughts?",
    actions: [
      { label: 'suggest something', value: 'what should I do?' },
      { label: 'just dumping', value: "just brain dumping, don't mind me" },
    ],
  },
  {
    patterns: [/easy/i, /small/i, /quick/i, /simple/i],
    response:
      "how about replying to that email from sarah? should only take a minute or two.",
    actions: [
      { label: 'done', value: "done with sarah's email" },
      { label: 'something else', value: 'give me something different' },
    ],
  },
]

const DEFAULT_RESPONSE = {
  response:
    "got it, saved. i'll keep track of that and bring it up when it makes sense.",
}

function findResponse(message: string): {
  response: string
  actions?: ActionButton[]
} {
  const match = MOCK_RESPONSES.find((r) =>
    r.patterns.some((p) => p.test(message)),
  )
  return match ?? DEFAULT_RESPONSE
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function mockSendMessage(
  message: string,
  onToken: (token: string) => void,
  onActions?: (actions: ActionButton[]) => void,
  onDone?: () => void,
): AbortController {
  const controller = new AbortController()
  const { response, actions } = findResponse(message)
  const words = response.split(' ')

  const initialDelay = 300 + Math.random() * 500

  void (async () => {
    await delay(initialDelay)
    if (controller.signal.aborted) return

    for (let i = 0; i < words.length; i++) {
      if (controller.signal.aborted) return
      const prefix = i === 0 ? '' : ' '
      onToken(prefix + words[i])
      await delay(30 + Math.random() * 30)
    }

    if (controller.signal.aborted) return

    if (actions && onActions) {
      onActions(actions)
    }

    onDone?.()
  })()

  return controller
}

export function mockFetchMessages(): Message[] {
  const now = Date.now()
  const min = 60_000
  const hour = 60 * min

  return [
    {
      id: 'mock-1',
      role: 'user',
      content: 'hey, just got to my desk. brain is everywhere today.',
      createdAt: new Date(now - 3 * hour).toISOString(),
    },
    {
      id: 'mock-2',
      role: 'assistant',
      content:
        "hey! no worries, let's work with that. want to dump everything out, or should i suggest something to start with?",
      createdAt: new Date(now - 3 * hour + 5000).toISOString(),
      actions: [
        { label: 'suggest something', value: 'what should I do?' },
        { label: 'just dumping', value: "brain dump time" },
      ],
    },
    {
      id: 'mock-3',
      role: 'user',
      content:
        "ok so i need to call the dentist, pick up groceries, there's that report due friday, and i think i forgot to reply to sarah's email",
      createdAt: new Date(now - 2.5 * hour).toISOString(),
    },
    {
      id: 'mock-4',
      role: 'assistant',
      content:
        "got all four. the report's the only one with a real deadline (friday). i'll keep the rest handy and surface them when the time feels right. you're good.",
      createdAt: new Date(now - 2.5 * hour + 4000).toISOString(),
    },
    {
      id: 'mock-5',
      role: 'user',
      content: 'what should i do first?',
      createdAt: new Date(now - 2 * hour).toISOString(),
    },
    {
      id: 'mock-6',
      role: 'assistant',
      content:
        "sarah's email — it's been sitting there and it's a quick one. knock it out and you'll feel lighter.",
      createdAt: new Date(now - 2 * hour + 3000).toISOString(),
      actions: [
        { label: 'done', value: "done with sarah's email" },
        { label: 'skip', value: 'skip that, what else?' },
      ],
    },
    {
      id: 'mock-7',
      role: 'user',
      content: 'done! that was easy',
      createdAt: new Date(now - 1.5 * hour).toISOString(),
    },
    {
      id: 'mock-8',
      role: 'assistant',
      content:
        "nice. see? one down, and you're rolling. want another one or taking a breather?",
      createdAt: new Date(now - 1.5 * hour + 3000).toISOString(),
      actions: [
        { label: "what's next?", value: 'what should I do next?' },
        { label: 'taking a break', value: "i'm going to take a break" },
      ],
    },
    {
      id: 'mock-9',
      role: 'user',
      content: "feeling kind of overwhelmed honestly. friday's report is stressing me out.",
      createdAt: new Date(now - 45 * min).toISOString(),
    },
    {
      id: 'mock-10',
      role: 'assistant',
      content:
        "totally valid. the report's not due until friday — that's two days away. you don't have to do it all now. want to spend just 20 minutes on an outline? no pressure beyond that.",
      createdAt: new Date(now - 45 * min + 5000).toISOString(),
    },
  ]
}
