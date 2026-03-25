interface VoiceButtonProps {
  isRecording: boolean
  isSupported: boolean
  onToggle: () => void
}

export function VoiceButton({ isRecording, isSupported, onToggle }: VoiceButtonProps) {
  if (!isSupported) return null

  return (
    <button
      onClick={onToggle}
      className={`w-10 h-10 flex items-center justify-center rounded-full transition-all duration-300 ${
        isRecording
          ? 'bg-error/20 text-error'
          : 'text-on-surface-variant hover:text-primary'
      }`}
      aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" x2="12" y1="19" y2="22" />
      </svg>
    </button>
  )
}
