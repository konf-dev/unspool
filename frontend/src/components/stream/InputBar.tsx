import { useState, useEffect, useRef, useCallback } from 'react'
import TextareaAutosize from 'react-textarea-autosize'
import { useVoice } from '@/hooks/useVoice'
import { MESSAGE_MAX_LENGTH } from '@/lib/constants'
import { VoiceButton } from './VoiceButton'

const DRAFT_KEY = 'unspool-draft'

interface InputBarProps {
  onSend: (message: string) => void
  onStop?: () => void
  isStreaming: boolean
  disabled?: boolean
}

export function InputBar({ onSend, onStop, isStreaming, disabled }: InputBarProps) {
  const [value, setValue] = useState(() => localStorage.getItem(DRAFT_KEY) ?? '')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { isRecording, isSupported, transcript, startRecording, stopRecording, clearTranscript } =
    useVoice()

  // Sync voice transcript into input
  useEffect(() => {
    if (transcript) {
      setValue(transcript)
    }
  }, [transcript])

  // Draft persistence with debounce — cancel pending save on send
  useEffect(() => {
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current)
    if (!value) return // Don't save empty string over a cleared draft
    draftTimerRef.current = setTimeout(() => {
      localStorage.setItem(DRAFT_KEY, value)
    }, 500)
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current)
    }
  }, [value])

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || isStreaming || disabled) return
    // Cancel any pending draft save before clearing
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current)
    onSend(trimmed)
    setValue('')
    clearTranscript()
    localStorage.removeItem(DRAFT_KEY)
    textareaRef.current?.focus()
  }, [value, isStreaming, disabled, onSend, clearTranscript])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleVoiceToggle = () => {
    if (isRecording) {
      stopRecording()
      if (navigator.vibrate) navigator.vibrate(10)
    } else {
      startRecording()
    }
  }

  const hasContent = value.trim().length > 0

  return (
    <footer className="px-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] bg-gradient-to-t from-background via-background/95 to-transparent pt-6">
      <div className="max-w-[640px] mx-auto">
        <div className="relative flex items-end bg-surface-container-low rounded-3xl p-2 transition-all duration-500 focus-within:bg-surface-container-high">
          <div className="flex-1 px-3 py-2">
            <TextareaAutosize
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value.slice(0, MESSAGE_MAX_LENGTH))}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? 'listening...' : "what's on your mind?"}
              maxRows={5}
              className="w-full bg-transparent border-none text-[15px] text-on-surface placeholder:text-on-surface-variant/40 resize-none leading-relaxed font-light focus:outline-none focus:ring-0"
              autoFocus
              disabled={disabled}
              aria-label="Message input"
            />
          </div>

          <div className="flex items-center gap-1">
            <VoiceButton
              isRecording={isRecording}
              isSupported={isSupported}
              onToggle={handleVoiceToggle}
            />

            {isStreaming ? (
              <button
                onClick={onStop}
                className="w-10 h-10 flex items-center justify-center bg-surface-bright text-on-surface rounded-full transition-all duration-300 hover:bg-surface-container-highest"
                aria-label="Stop generating"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                  <rect width="14" height="14" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!hasContent || disabled}
                className={`w-10 h-10 flex items-center justify-center rounded-full transition-all duration-300 ${
                  hasContent
                    ? 'bg-primary text-on-primary hover:scale-95 active:scale-90 shadow-lg shadow-primary/10'
                    : 'text-on-surface-variant/30'
                }`}
                aria-label="Send message"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="12" y1="19" x2="12" y2="5" />
                  <polyline points="5 12 12 5 19 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </footer>
  )
}
