import { useState, useCallback } from 'react'
import { getApiUrl } from '../lib/api'
import './PaymentPrompt.css'

interface PaymentPromptProps {
  token: string
  onDismiss: (message: string) => void
}

export function PaymentPrompt({ token, onDismiss }: PaymentPromptProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handleSubscribe = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${getApiUrl()}/api/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })

      if (!response.ok) throw new Error('Subscribe failed')

      const data = (await response.json()) as { url: string }
      window.open(data.url, '_blank', 'noopener,noreferrer')
    } catch {
      onDismiss("something went wrong with the payment link. try again in a bit.")
    } finally {
      setIsLoading(false)
    }
  }, [token, onDismiss])

  const handleDismiss = useCallback(() => {
    onDismiss("no worries at all. you've still got free messages today. i'm here whenever you need me.")
  }, [onDismiss])

  return (
    <div className="message-row assistant">
      <div className="payment-prompt">
        <p className="payment-prompt-text">
          you've been using unspool a lot today — love that. want to go unlimited so there's no cap?
        </p>
        <div className="payment-prompt-actions">
          <button
            className="payment-btn primary"
            type="button"
            onClick={() => void handleSubscribe()}
            disabled={isLoading}
            aria-label="Subscribe for unlimited messages"
          >
            {isLoading ? 'opening...' : 'go unlimited — $8/mo'}
          </button>
          <button
            className="payment-btn secondary"
            type="button"
            onClick={handleDismiss}
            disabled={isLoading}
            aria-label="Dismiss subscription prompt"
          >
            not now
          </button>
        </div>
      </div>
    </div>
  )
}
