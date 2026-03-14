import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import TextareaAutosize from 'react-textarea-autosize'
import { MESSAGE_MAX_LENGTH } from '../lib/constants'
import { useVoice } from '../hooks/useVoice'
import { VoiceInput } from './VoiceInput'
import './InputBar.css'

interface InputBarProps {
  onSend: (message: string) => void
  isStreaming: boolean
  onStop: () => void
}

export function InputBar({ onSend, isStreaming, onStop }: InputBarProps) {
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
    if (!trimmed) return
    navigator.vibrate?.(10)
    onSend(trimmed)
    setValue('')
    requestAnimationFrame(() => textareaRef.current?.focus())
  }, [value, onSend])

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

  const renderButton = () => {
    if (hasText) {
      return (
        <button
          className="input-bar-send"
          type="button"
          onClick={handleSend}
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
      )
    }

    if (isStreaming) {
      return (
        <button
          className="input-bar-stop"
          type="button"
          onClick={onStop}
          aria-label="Stop generating"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <rect width="14" height="14" rx="2" fill="#fff" />
          </svg>
        </button>
      )
    }

    return (
      <VoiceInput
        isRecording={isRecording}
        isSupported={isSupported}
        onToggle={handleVoiceToggle}
      />
    )
  }

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
        />
        {renderButton()}
      </div>
    </div>
  )
}
