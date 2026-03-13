import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import TextareaAutosize from 'react-textarea-autosize'
import { MESSAGE_MAX_LENGTH } from '../lib/constants'
import { useVoice } from '../hooks/useVoice'
import { VoiceInput } from './VoiceInput'
import './InputBar.css'

interface InputBarProps {
  onSend: (message: string) => void
  disabled: boolean
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { isRecording, isSupported, transcript, startRecording, stopRecording, clearTranscript } =
    useVoice()

  useEffect(() => {
    if (transcript) {
      setValue(transcript)
      stopRecording()
      clearTranscript()
      textareaRef.current?.focus()
    }
  }, [transcript, stopRecording, clearTranscript])

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    requestAnimationFrame(() => textareaRef.current?.focus())
  }, [value, disabled, onSend])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleVoiceToggle = useCallback(() => {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }, [isRecording, startRecording, stopRecording])

  const hasText = value.trim().length > 0
  const placeholder = isRecording ? 'listening...' : "what's on your mind?"

  return (
    <div className="input-bar-wrapper">
      <div className="input-bar-fade" />
      <div className="input-bar">
        <TextareaAutosize
          ref={textareaRef}
          className="input-bar-textarea"
          value={value}
          maxLength={MESSAGE_MAX_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          minRows={1}
          maxRows={4}
          disabled={disabled}
        />
        {hasText ? (
          <button
            className="input-bar-send"
            type="button"
            onClick={handleSend}
            disabled={disabled}
            aria-label="Send message"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M5 12L12 5L19 12M12 5V19"
                stroke="#fff"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : (
          <VoiceInput
            isRecording={isRecording}
            isSupported={isSupported}
            onToggle={handleVoiceToggle}
          />
        )}
      </div>
    </div>
  )
}
