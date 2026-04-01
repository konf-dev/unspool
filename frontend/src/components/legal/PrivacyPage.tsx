import { useUIStore } from '@/stores/uiStore'

export function PrivacyPage() {
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
        Privacy Policy
      </h1>

      <div className="text-on-surface-variant font-light text-sm leading-[1.8] space-y-6">
        <p>
          <strong className="text-on-surface font-medium">Last updated:</strong> March 2026
        </p>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">What we collect</h2>
          <p>
            Unspool stores your messages and the items extracted from them in a secure graph
            database. We use Google's Gemini API to process your messages. Your data is scoped
            to your account and is never shared with other users.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Authentication</h2>
          <p>
            We use Supabase for authentication. When you sign in with Google, we may request
            calendar read access to help surface upcoming events. Calendar data is only used to
            inform your personal context and is never stored permanently.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">AI processing</h2>
          <p>
            Your messages are processed alongside your recent conversation history and extracted
            context (tasks, deadlines, preferences) to provide relevant responses. This data is
            sent to our AI provider (Google Gemini) but is not used to train AI models.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Data deletion</h2>
          <p>
            You can delete your account and all associated data at any time. This is a permanent,
            irreversible action that removes all messages, graph data, and profile information.
            To delete your account, just say "delete my account" in the chat.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-on-surface font-medium text-base">Push notifications</h2>
          <p>
            If you opt in, we send push notifications for proactive reminders (approaching
            deadlines, check-ins). You can disable these at any time through your device settings.
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
