import './VoiceInput.css'

interface VoiceInputProps {
  isRecording: boolean
  isSupported: boolean
  onToggle: () => void
}

export function VoiceInput({ isRecording, isSupported, onToggle }: VoiceInputProps) {
  if (!isSupported) return null

  const strokeColor = isRecording ? 'var(--color-accent)' : 'var(--color-text-muted)'

  return (
    <button
      className={`voice-input-btn ${isRecording ? 'recording' : ''}`}
      type="button"
      onClick={onToggle}
      aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M12 2C10.34 2 9 3.34 9 5V12C9 13.66 10.34 15 12 15C13.66 15 15 13.66 15 12V5C15 3.34 13.66 2 12 2Z"
          stroke={strokeColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M5 10V12C5 15.87 8.13 19 12 19C15.87 19 19 15.87 19 12V10"
          stroke={strokeColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M12 19V22"
          stroke={strokeColor}
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </button>
  )
}
