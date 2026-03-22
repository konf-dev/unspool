import './LegalPage.css'

interface LegalPageProps {
  title: string
  children: React.ReactNode
  onBack: () => void
}

export function LegalPage({ title, children, onBack }: LegalPageProps) {
  return (
    <div className="legal-page">
      <div className="stars">
        <div className="stars-small" />
        <div className="stars-medium" />
        <div className="stars-large" />
      </div>

      <div className="legal-content">
        <button
          className="legal-back"
          type="button"
          onClick={onBack}
        >
          &larr; back
        </button>

        <h1 className="legal-title">{title}</h1>
        <div className="legal-body">
          {children}
        </div>
      </div>
    </div>
  )
}

export function PrivacyPage({ onBack }: { onBack: () => void }) {
  return (
    <LegalPage title="privacy policy" onBack={onBack}>
      <p className="legal-updated">Last updated: March 2026</p>

      <h2>What we collect</h2>
      <p>
        When you use Unspool, we store your messages, tasks, and preferences
        to provide the service. We use your email address for authentication
        and account recovery.
      </p>
      <p>
        If you connect Google Calendar, we read your calendar events
        (read-only) to help surface relevant tasks. We never modify your
        calendar.
      </p>

      <h2>How we use your data</h2>
      <p>
        Your messages are sent to AI providers (currently OpenAI and/or
        Anthropic) to generate responses. These providers process your
        messages according to their own privacy policies but do not use
        your data for training.
      </p>
      <p>
        We track anonymous usage metrics (message counts, latency, token
        usage) to improve the service. We never sell your personal data.
      </p>

      <h2>Data storage</h2>
      <p>
        Your data is stored in Supabase (hosted on AWS) with row-level
        security. All data is encrypted in transit (TLS) and at rest.
      </p>

      <h2>Your rights</h2>
      <p>
        You can delete all your data at any time from within the app. This
        is permanent and irreversible — we delete everything across all
        tables immediately.
      </p>
      <p>
        For questions or data requests, email{' '}
        <a href="mailto:privacy@unspool.life">privacy@unspool.life</a>.
      </p>
    </LegalPage>
  )
}

export function TermsPage({ onBack }: { onBack: () => void }) {
  return (
    <LegalPage title="terms of service" onBack={onBack}>
      <p className="legal-updated">Last updated: March 2026</p>

      <h2>The service</h2>
      <p>
        Unspool is an AI personal assistant. It helps you keep track of
        tasks, ideas, and reminders through conversation. It is not a
        medical device, therapist, or emergency service.
      </p>

      <h2>Your account</h2>
      <p>
        You need a Google account or email address to use Unspool. You are
        responsible for keeping your account secure. One account per person.
      </p>

      <h2>Free and paid tiers</h2>
      <p>
        The free tier allows 10 messages per day. The unlimited tier is
        $8/month, billed through Stripe. You can cancel anytime — your
        access continues through the end of the billing period.
      </p>

      <h2>AI limitations</h2>
      <p>
        The AI may occasionally misunderstand, misclassify, or forget
        things. Do not rely on Unspool as your sole reminder system for
        critical deadlines (medication, legal deadlines, etc). Use it
        alongside your existing systems until you're comfortable.
      </p>

      <h2>Acceptable use</h2>
      <p>
        Don't use Unspool to store illegal content, harass others, or
        attempt to exploit the AI system. We reserve the right to suspend
        accounts that violate these terms.
      </p>

      <h2>Data deletion</h2>
      <p>
        You can delete your account and all associated data at any time.
        Deletion is permanent and cannot be undone.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. Continued use after changes constitutes
        acceptance. We'll notify you of significant changes via the app.
      </p>

      <p>
        Questions? Email{' '}
        <a href="mailto:hello@unspool.life">hello@unspool.life</a>.
      </p>
    </LegalPage>
  )
}
