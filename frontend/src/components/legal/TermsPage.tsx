import { useUIStore } from '@/stores/uiStore'

export function TermsPage() {
  const navigate = useUIStore((s) => s.navigate)

  return (
    <div className="min-h-screen bg-background px-8 py-16 max-w-2xl mx-auto">
      <button
        onClick={() => navigate('landing')}
        className="text-on-surface-variant text-sm mb-8 hover:text-on-surface transition-colors"
      >
        &larr; back
      </button>

      <h1 className="text-on-surface font-extralight text-3xl tracking-tight mb-8">
        Terms of Service
      </h1>

      <div className="text-on-surface-variant font-light text-sm leading-[1.8] space-y-6">
        <p>
          <strong className="text-on-surface font-medium">Last updated:</strong> March 2026
        </p>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">What Unspool is</h2>
          <p>
            Unspool is an AI-powered personal assistant that helps you keep track of tasks,
            thoughts, and commitments through natural conversation. It is not a medical device,
            therapist, or substitute for professional advice.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Your content</h2>
          <p>
            You own everything you put into Unspool. We store your messages and extracted data
            solely to provide the service. We do not sell, share, or use your content for
            advertising.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">AI limitations</h2>
          <p>
            Unspool uses AI (Google Gemini) to process your messages. AI responses may
            occasionally be inaccurate or miss context. Unspool should not be relied upon for
            critical scheduling, medical, legal, or financial decisions.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Subscription</h2>
          <p>
            Unspool offers a free tier with limited daily messages and a paid tier ($8/month)
            with unlimited usage. Subscriptions are managed through Stripe and can be cancelled
            at any time.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Account deletion</h2>
          <p>
            You may delete your account at any time through the app. Deletion is permanent
            and removes all stored data within 30 days.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Contact</h2>
          <p>
            Questions? Reach us at{' '}
            <a href="mailto:hello@unspool.life" className="text-primary underline underline-offset-4 decoration-primary/30">
              hello@unspool.life
            </a>
          </p>
        </section>
      </div>
    </div>
  )
}
