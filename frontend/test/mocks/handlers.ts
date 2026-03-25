import { http, HttpResponse } from 'msw'

export const handlers = [
  // Chat SSE endpoint
  http.post('*/api/chat', () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        const events = [
          { type: 'token', content: "I'm " },
          { type: 'token', content: 'finishing ' },
          { type: 'token', content: 'the report ' },
          { type: 'token', content: 'by Friday.' },
          { type: 'done' },
        ]

        let i = 0
        const interval = setInterval(() => {
          if (i >= events.length) {
            clearInterval(interval)
            controller.close()
            return
          }
          const data = `data: ${JSON.stringify(events[i])}\n\n`
          controller.enqueue(encoder.encode(data))
          i++
        }, 50)
      },
    })

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    })
  }),

  // Messages endpoint
  http.get('*/api/messages', () => {
    return HttpResponse.json({
      messages: [
        {
          id: '1',
          user_id: 'mock-user',
          role: 'user',
          content: 'I need to finish the report by Friday',
          created_at: new Date().toISOString(),
          metadata: null,
        },
        {
          id: '2',
          user_id: 'mock-user',
          role: 'assistant',
          content: "I'm finishing the report by Friday. Got it.",
          created_at: new Date().toISOString(),
          metadata: null,
        },
      ],
      has_more: false,
    })
  }),

  // Demo chat
  http.post('*/api/demo-chat', () => {
    return HttpResponse.json({
      content: 'got it. what else is on your mind?',
      shouldPromptSignIn: false,
    })
  }),

  // Health check
  http.get('*/health', () => {
    return HttpResponse.json({ status: 'ok' })
  }),
]
