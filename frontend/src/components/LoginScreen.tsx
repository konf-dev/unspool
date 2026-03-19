import { useState, useEffect, useCallback } from 'react'
import './LoginScreen.css'

interface LoginScreenProps {
  onSignInWithGoogle: () => Promise<void>
  onSignInWithEmail: (email: string) => Promise<void>
}

export function LoginScreen({ onSignInWithGoogle, onSignInWithEmail }: LoginScreenProps) {
  const [showEmail, setShowEmail] = useState(false)
  const [email, setEmail] = useState('')
  const [emailSent, setEmailSent] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => {
      setCooldown((prev) => prev - 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  const handleGoogleSignIn = useCallback(async () => {
    setError(null)
    try {
      await onSignInWithGoogle()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'sign in failed'
      setError(message)
    }
  }, [onSignInWithGoogle])

  const handleEmailSignIn = useCallback(async () => {
    if (!email.trim() || cooldown > 0 || isSubmitting) return

    setError(null)
    setIsSubmitting(true)

    try {
      await onSignInWithEmail(email.trim())
      setEmailSent(true)
      setCooldown(30)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'failed to send magic link'
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }, [email, cooldown, isSubmitting, onSignInWithEmail])

  const handleEmailKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        void handleEmailSignIn()
      }
    },
    [handleEmailSignIn],
  )

  return (
    <div className="login-screen">
      <div className="stars">
        <div className="stars-small" />
        <div className="stars-medium" />
        <div className="stars-large" />
      </div>

      <svg
        className="login-hills"
        viewBox="0 0 1440 500"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M0 380 Q200 280 400 340 Q600 400 800 320 Q1000 240 1200 300 Q1400 360 1440 330 L1440 500 L0 500 Z"
          fill="#000"
        />
        <path
          d="M0 420 Q250 350 500 390 Q750 430 1000 370 Q1200 310 1440 380 L1440 500 L0 500 Z"
          fill="#000"
        />
        <path
          d="M0 460 Q300 400 600 440 Q900 480 1200 430 Q1350 410 1440 440 L1440 500 L0 500 Z"
          fill="#000"
        />
      </svg>

      <div className="login-content">
        <h1 className="login-title">unspool</h1>
        <p className="login-tagline">let your mind unspool</p>

        <div className="login-actions">
          <button
            className="login-btn-google"
            type="button"
            onClick={() => void handleGoogleSignIn()}
          >
            continue with Google
          </button>

          <button
            className="login-email-toggle"
            type="button"
            onClick={() => setShowEmail((prev) => !prev)}
          >
            or continue with email
          </button>

          <div
            className={`login-email-form ${showEmail ? 'expanded' : ''}`}
          >
            {emailSent ? (
              <p className="login-email-sent">
                check your email for a magic link
                {cooldown > 0 && (
                  <span className="login-cooldown">
                    {' '}
                    (resend in {cooldown}s)
                  </span>
                )}
              </p>
            ) : null}
            <input
              className="login-email-input"
              type="email"
              placeholder="your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={handleEmailKeyDown}
              autoComplete="email"
            />
            <button
              className="login-btn-magic"
              type="button"
              onClick={() => void handleEmailSignIn()}
              disabled={!email.trim() || cooldown > 0 || isSubmitting}
            >
              {cooldown > 0
                ? `resend in ${cooldown}s`
                : isSubmitting
                  ? 'sending...'
                  : 'send magic link'}
            </button>
          </div>

          {error && (
            <div className="login-error">{error}</div>
          )}
        </div>
      </div>
    </div>
  )
}
