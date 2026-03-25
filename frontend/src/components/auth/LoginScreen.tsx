import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import { AmbientGlow } from '@/components/shared/AmbientGlow'

type Stage = 'email' | 'otp'

const OTP_LENGTH = 6

export function LoginScreen() {
  const { sendOtp, verifyOtp } = useAuthStore()
  const navigate = useUIStore((s) => s.navigate)
  const [stage, setStage] = useState<Stage>('email')
  const [email, setEmail] = useState(() => sessionStorage.getItem('unspool-otp-email') ?? '')
  const [otp, setOtp] = useState('')
  const [error, setError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [isVerifying, setIsVerifying] = useState(false)
  const otpInputRef = useRef<HTMLInputElement>(null)

  // Persist email across refreshes so user doesn't lose context
  useEffect(() => {
    if (email) sessionStorage.setItem('unspool-otp-email', email)
  }, [email])

  // Auto-focus OTP input when stage changes
  useEffect(() => {
    if (stage === 'otp') {
      otpInputRef.current?.focus()
    }
  }, [stage])

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || isSending) return
    setError('')
    setIsSending(true)

    try {
      await sendOtp(email.trim())
      setStage('otp')
    } catch (err) {
      setError('Failed to send code. Please try again.')
      console.error(err)
    } finally {
      setIsSending(false)
    }
  }

  // #7: Use ref to prevent double-submit (state updates are async, ref is synchronous)
  const isVerifyingRef = useRef(false)
  const handleVerify = useCallback(async (code: string) => {
    if (code.length !== OTP_LENGTH || isVerifyingRef.current) return
    isVerifyingRef.current = true
    setError('')
    setIsVerifying(true)

    try {
      await verifyOtp(email.trim(), code)
      sessionStorage.removeItem('unspool-otp-email')
      // onAuthStateChange will update store → App.tsx will redirect to /chat
    } catch (err) {
      setError('Invalid or expired code. Try again.')
      setOtp('')
      otpInputRef.current?.focus()
      console.error(err)
    } finally {
      isVerifyingRef.current = false
      setIsVerifying(false)
    }
  }, [email, verifyOtp])

  const handleOtpChange = (value: string) => {
    // Only allow digits
    const digits = value.replace(/\D/g, '').slice(0, OTP_LENGTH)
    setOtp(digits)

    // Auto-submit when all digits entered
    if (digits.length === OTP_LENGTH) {
      void handleVerify(digits)
    }
  }

  const handleResend = async () => {
    setError('')
    setOtp('')
    setIsSending(true)
    try {
      await sendOtp(email.trim())
      setError('')
    } catch (err) {
      setError('Failed to resend. Please try again.')
      console.error(err)
    } finally {
      setIsSending(false)
    }
  }

  return (
    <main className="relative min-h-screen flex flex-col items-center justify-between px-8 py-16 overflow-hidden">
      <AmbientGlow />

      <header className="flex flex-col items-center mt-24 z-10">
        <h1 className="text-on-surface font-extralight text-5xl tracking-[-0.04em] leading-none mb-3">
          unspool
        </h1>
        <p className="text-on-surface-variant font-light text-sm tracking-[0.05em] opacity-80">
          your mind, but reliable
        </p>
      </header>

      <div className="w-full max-w-sm flex flex-col items-center gap-10 z-10">
        <div className="w-16 h-px bg-gradient-to-r from-transparent via-outline-variant/30 to-transparent" />

        {error && (
          <p className="text-error text-sm text-center animate-fade-in">{error}</p>
        )}

        {stage === 'email' ? (
          <form onSubmit={(e) => void handleSendCode(e)} className="w-full flex flex-col gap-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              autoFocus
              autoComplete="email"
              required
              className="w-full h-14 bg-surface-container-low text-on-surface rounded-full px-6 text-sm font-light placeholder:text-on-surface-variant/40 focus:outline-none ghost-border"
            />
            <button
              type="submit"
              disabled={isSending || !email.trim()}
              className="w-full h-14 bg-primary text-on-primary rounded-full font-medium text-[15px] tracking-wide flex items-center justify-center transition-all duration-500 hover:bg-primary-dim active:scale-[0.98] disabled:opacity-50"
            >
              {isSending ? 'sending...' : 'send login code'}
            </button>
          </form>
        ) : (
          <div className="w-full flex flex-col items-center gap-6 animate-fade-in">
            <div className="text-center space-y-1">
              <p className="text-on-surface text-sm">enter the 6-digit code</p>
              <p className="text-on-surface-variant text-xs">
                sent to {email}
              </p>
            </div>

            <input
              ref={otpInputRef}
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="one-time-code"
              value={otp}
              onChange={(e) => handleOtpChange(e.target.value)}
              maxLength={OTP_LENGTH}
              disabled={isVerifying}
              className="w-48 h-16 bg-surface-container-low text-on-surface text-center text-2xl font-light tracking-[0.5em] rounded-2xl focus:outline-none ghost-border disabled:opacity-50"
              aria-label="Login code"
            />

            {isVerifying && (
              <p className="text-on-surface-variant text-xs animate-pulse-sage">verifying...</p>
            )}

            <div className="flex flex-col items-center gap-3 mt-2">
              <button
                onClick={() => void handleResend()}
                disabled={isSending}
                className="text-on-surface-variant text-xs tracking-wide hover:text-on-surface transition-colors disabled:opacity-50"
              >
                {isSending ? 'sending...' : 'resend code'}
              </button>
              <button
                onClick={() => {
                  setStage('email')
                  setOtp('')
                  setError('')
                }}
                className="text-on-surface-variant/40 text-xs tracking-wide hover:text-on-surface-variant transition-colors"
              >
                use a different email
              </button>
            </div>
          </div>
        )}
      </div>

      <footer className="w-full flex flex-col items-center gap-6 z-10">
        <div className="w-1 h-1 rounded-full bg-primary/20" />
        <nav className="flex items-center gap-4 text-[11px] font-light tracking-[0.1em] text-on-surface-variant/40 uppercase">
          <button
            onClick={() => navigate('privacy')}
            className="hover:text-on-surface-variant transition-colors duration-300"
          >
            privacy
          </button>
          <span className="opacity-20">&middot;</span>
          <button
            onClick={() => navigate('terms')}
            className="hover:text-on-surface-variant transition-colors duration-300"
          >
            terms
          </button>
        </nav>
      </footer>
    </main>
  )
}
