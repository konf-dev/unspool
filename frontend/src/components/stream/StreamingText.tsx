import { useMemo } from 'react'
import Markdown from 'markdown-to-jsx'

interface StreamingTextProps {
  content: string
}

// Buffer incomplete markdown action patterns to prevent flickering
function bufferContent(raw: string): string {
  // If it ends with an incomplete [label](action:... pattern, hold it
  const incompleteAction = /\[[^\]]*$/.exec(raw)
  if (incompleteAction) {
    return raw.slice(0, incompleteAction.index)
  }
  return raw
}

export function StreamingText({ content }: StreamingTextProps) {
  const buffered = useMemo(() => bufferContent(content), [content])

  if (!buffered) {
    return (
      <div className="pl-6">
        <span className="inline-block w-0.5 h-4 bg-primary animate-cursor-blink" />
      </div>
    )
  }

  return (
    <div className="pl-6 text-[15px] leading-[1.8] text-on-surface-variant font-light">
      <Markdown
        options={{
          forceBlock: true,
          overrides: {
            p: { props: { className: 'mb-2 last:mb-0' } },
            ul: { props: { className: 'flex flex-col gap-2 mb-2' } },
            li: {
              component: ({ children }) => (
                <li className="flex gap-2">
                  <span className="text-primary">&#8226;</span>
                  <span>{children}</span>
                </li>
              ),
            },
            strong: { props: { className: 'font-medium text-on-surface' } },
          },
        }}
      >
        {buffered}
      </Markdown>
      <span className="inline-block w-0.5 h-4 bg-primary animate-cursor-blink ml-0.5 align-middle" />
    </div>
  )
}
