import { useState, useRef, useCallback, useEffect } from 'react'

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList
  resultIndex: number
}

interface SpeechRecognitionErrorEvent {
  error: string
}

interface SpeechRecognitionInstance {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance
}

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  const w = window as unknown as Record<string, unknown>
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition) as SpeechRecognitionConstructor | null
}

interface UseVoiceReturn {
  isRecording: boolean
  isSupported: boolean
  transcript: string
  startRecording: () => void
  stopRecording: () => void
  clearTranscript: () => void
}

export function useVoice(): UseVoiceReturn {
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalStopRef = useRef(false)

  const isSupported = getSpeechRecognition() !== null

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current !== null) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }, [])

  const resetSilenceTimer = useCallback(() => {
    clearSilenceTimer()
    silenceTimerRef.current = setTimeout(() => {
      intentionalStopRef.current = true
      recognitionRef.current?.stop()
      setIsRecording(false)
    }, 3000)
  }, [clearSilenceTimer])

  const stopRecording = useCallback(() => {
    intentionalStopRef.current = true
    clearSilenceTimer()
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setIsRecording(false)
  }, [clearSilenceTimer])

  const startRecording = useCallback(() => {
    const SpeechRecognitionCtor = getSpeechRecognition()
    if (!SpeechRecognitionCtor) return

    intentionalStopRef.current = false
    const recognition = new SpeechRecognitionCtor()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = ''
      let interimTranscript = ''

      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i]
        if (result?.[0]) {
          if (result.isFinal) {
            finalTranscript += result[0].transcript
          } else {
            interimTranscript += result[0].transcript
          }
        }
      }

      setTranscript(finalTranscript + interimTranscript)
      resetSilenceTimer()
    }

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error('Speech recognition error:', event.error)
      clearSilenceTimer()
      setIsRecording(false)
      recognitionRef.current = null
    }

    recognition.onend = () => {
      if (!intentionalStopRef.current && recognitionRef.current) {
        try {
          recognitionRef.current.start()
        } catch {
          setIsRecording(false)
          recognitionRef.current = null
        }
      } else {
        recognitionRef.current = null
      }
    }

    recognitionRef.current = recognition

    try {
      recognition.start()
      setIsRecording(true)
      resetSilenceTimer()
      // Haptic feedback
      if (navigator.vibrate) navigator.vibrate(10)
    } catch {
      setIsRecording(false)
      recognitionRef.current = null
    }
  }, [resetSilenceTimer, clearSilenceTimer])

  const clearTranscript = useCallback(() => {
    setTranscript('')
  }, [])

  useEffect(() => {
    return () => {
      clearSilenceTimer()
      if (recognitionRef.current) {
        intentionalStopRef.current = true
        recognitionRef.current.stop()
        recognitionRef.current = null
      }
    }
  }, [clearSilenceTimer])

  return {
    isRecording,
    isSupported,
    transcript,
    startRecording,
    stopRecording,
    clearTranscript,
  }
}
