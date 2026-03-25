import { memo } from 'react'
import type { Message } from '@/types'

interface UserThoughtProps {
  message: Message
}

export const UserThought = memo(function UserThought({ message }: UserThoughtProps) {
  return (
    <div className="animate-fade-in flex justify-end">
      <div className="bg-user-bubble px-5 py-4 rounded-3xl rounded-tr-none ml-12">
        <p className="text-[15px] leading-relaxed text-on-surface font-normal tracking-tight">
          {message.content}
        </p>
        {message.status === 'queued' && (
          <span className="text-[10px] text-on-surface-variant/40 tracking-wider mt-1 block">
            queued
          </span>
        )}
      </div>
    </div>
  )
})
