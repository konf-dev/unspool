import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import TextareaAutosize from 'react-textarea-autosize'
import { MESSAGE_MAX_LENGTH } from '../lib/constants'
import { useVoice } from '../hooks/useVoice'
import { VoiceInput } from './VoiceInput'
import './InputBar.css'

const DRAFT_KEY = 'unspool-draft'
const HINT_KEY = 'unspool-shift-enter-hint-dismissed'

interface InputBarProps {
  onSend: (message: string) => void
  isStreaming: boolean
  onStop: () => void
}

export function InputBar({ onSend, isStreaming, onStop }: InputBarProps) {
  const [value, setValue] = useState(() => localStorage.getItem(DRAFT_KEY) ?? '')
  const [showHint, setShowHint] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hintDismissedRef = useRef(localStorage.getItem(HINT_KEY) === 'true')
  const sendCountRef = useRef(0)
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
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

  // Draft auto-save (debounced 500ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (value.trim()) {
        localStorage.setItem(DRAFT_KEY, value)
      } else {
        localStorage.removeItem(DRAFT_KEY)
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [value])

  const dismissHint = useCallback(() => {
    setShowHint(false)
    hintDismissedRef.current = true
    localStorage.setItem(HINT_KEY, 'true')
    if (hintTimerRef.current) {
      clearTimeout(hintTimerRef.current)
      hintTimerRef.current = null
    }
  }, [])

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed) return
    navigator.vibrate?.(10)
    onSend(trimmed)
    setValue('')
    localStorage.removeItem(DRAFT_KEY)
    requestAnimationFrame(() => textareaRef.current?.focus())

    sendCountRef.current += 1
    if (
      sendCountRef.current === 1 &&
      !hintDismissedRef.current &&
      !window.matchMedia('(pointer: coarse)').matches
    ) {
      setShowHint(true)
      hintTimerRef.current = setTimeout(dismissHint, 8000)
    }
  }, [value, onSend, dismissHint])

  const isTouchDevice = useRef(window.matchMedia('(pointer: coarse)').matches)

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey && !isTouchDevice.current) {
        e.preventDefault()
        handleSend()
      }
      if (e.key === 'Enter' && e.shiftKey && showHint) {
        dismissHint()
      }
    },
    [handleSend, showHint, dismissHint],
  )

  const handleVoiceToggle = useCallback(() => {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }, [isRecording, startRecording, stopRecording])

  useEffect(() => {
    return () => {
      if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
    }
  }, [])

  const hasText = value.trim().length > 0
  const placeholder = isRecording ? 'listening...' : "what's on your mind?"

  const renderButton = () => {
    return (
      <div className="input-bar-buttons">
        {isStreaming && (
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
        )}
        {hasText ? (
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
        ) : (
          !isStreaming && (
            <VoiceInput
              isRecording={isRecording}
              isSupported={isSupported}
              onToggle={handleVoiceToggle}
            />
          )
        )}
      </div>
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
      {showHint && <div className="input-hint">shift+enter for new line</div>}
    </div>
  )
}
