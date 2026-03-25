import { memo } from 'react'
import Markdown from 'markdown-to-jsx'
import type { Message } from '@/types'
import { ActionChips } from './ActionChips'

interface ReflectionProps {
  message: Message
  onAction?: (action: { label: string; value: string }) => void
}

export const Reflection = memo(function Reflection({ message, onAction }: ReflectionProps) {
  const isError = message.metadata?.type === 'error'
  const isProactive = message.metadata?.type === 'proactive'

  return (
    <div className="pl-6 animate-fade-in border-l-2 border-primary/10">
      {isProactive && (
        <span className="text-[10px] tracking-wider text-primary/50 uppercase mb-1 block">
          welcome back
        </span>
      )}
      <div
        className={`text-[15px] leading-[1.8] font-light ${
          isError ? 'text-error/80' : 'text-on-surface-variant'
        }`}
      >
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
              a: {
                props: {
                  className: 'text-primary underline decoration-primary/30 underline-offset-4',
                  target: '_blank',
                  rel: 'noopener noreferrer',
                },
              },
              strong: { props: { className: 'font-medium text-on-surface' } },
              code: {
                props: {
                  className: 'bg-surface-container-high px-1.5 py-0.5 rounded text-sm font-mono',
                },
              },
            },
          }}
        >
          {message.content}
        </Markdown>
      </div>
      {message.actions && message.actions.length > 0 && onAction && (
        <ActionChips actions={message.actions} onAction={onAction} />
      )}
    </div>
  )
})
