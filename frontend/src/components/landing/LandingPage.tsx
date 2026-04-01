import { useUIStore } from '@/stores/uiStore'
import { DemoChat } from './DemoChat'

export function LandingPage() {
  const navigate = useUIStore((s) => s.navigate)

  return (
    <div className="flex flex-col min-h-screen overflow-x-hidden">
      {/* Drag handle */}
      <header className="fixed top-0 left-0 right-0 z-50 flex justify-center items-start h-12 bg-transparent">
        <div className="w-10 h-1 mt-4 rounded-full bg-surface-container-high" />
      </header>

      <main className="flex-grow flex flex-col items-center px-8 pt-8 pb-16 sm:pt-14 sm:pb-32 max-w-lg mx-auto w-full text-center">
        {/* Title */}
        <section className="mb-6 sm:mb-10">
          <h1 className="text-[2.5rem] font-extralight tracking-[0.2em] text-on-surface mb-2">
            unspool
          </h1>
          <p className="text-on-surface-variant text-sm tracking-wide leading-relaxed">
            you don't organize anything. you just talk.
          </p>
        </section>

        {/* Demo */}
        <section className="w-full mb-6 sm:mb-12">
          <DemoChat onSignIn={() => navigate('login')} />
        </section>

        {/* Why this exists */}
        <section className="w-full text-left mb-10 sm:mb-14 space-y-6">
          <h2 className="text-on-surface-variant/50 text-[10px] tracking-[0.15em] uppercase text-center mb-4">
            why this exists
          </h2>

          <div className="space-y-5">
            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                every app asks me to organize first.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                where does this go? what category? what priority? each decision costs energy I don't have. the organizing <em>is</em> the bottleneck.
              </p>
            </div>

            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                categories don't match how my brain works.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                when executive dysfunction hits, taking out the garbage and filing taxes are the same difficulty. "work" vs "personal" is meaningless. it's all one wall.
              </p>
            </div>

            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                I spend hours setting up systems I'll use for three days.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                beautiful databases, color-coded planners, the perfect template. the setup feels productive. it isn't.
              </p>
            </div>

            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                abandoned systems become guilt.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                unchecked boxes, half-filled tables, empty pages. opening the app triggers shame. so I quit and feel worse.
              </p>
            </div>

            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                I don't live by the clock.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                my sleep schedule is random. my energy is random. "plan your morning" means nothing when morning is a moving target. unspool doesn't care what time it is — it works when you show up.
              </p>
            </div>

            <div>
              <p className="text-on-surface text-sm font-medium leading-relaxed">
                every notification is a guilt trip.
              </p>
              <p className="text-on-surface-variant text-sm font-light leading-relaxed mt-1">
                unspool only speaks up when something actually matters. days of silence means nothing is urgent. that's the app working correctly.
              </p>
            </div>
          </div>

          <p className="text-on-surface-variant/70 text-xs leading-relaxed text-center pt-2">
            this is not a productivity app. it just helps me get by.
</p>
        </section>

        {/* CTAs */}
        <section className="flex flex-col items-center gap-6 w-full">
          <button
            onClick={() => navigate('login')}
            className="w-full bg-primary text-on-primary py-4 rounded-full font-semibold tracking-wide hover:brightness-105 transition-all duration-300"
          >
            Get Started
          </button>
          <button
            onClick={() => navigate('login')}
            className="text-on-surface-variant text-sm tracking-wide hover:text-on-surface transition-colors"
          >
            already have an account?{' '}
            <span className="underline decoration-outline-variant/30 underline-offset-4">
              sign in
            </span>
          </button>
          <div className="mt-12 space-y-4">
            <p className="text-on-surface-variant text-sm leading-relaxed tracking-[0.02em]">
              no lists. no dashboards. nothing to maintain. ever.
            </p>
            <p className="text-on-surface-variant/50 text-[10px] tracking-[0.1em] uppercase">
              free during early access
            </p>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative w-full overflow-hidden">
        <div className="relative z-10 flex justify-center gap-6 py-8 pb-12">
          <button
            onClick={() => navigate('privacy')}
            className="text-[10px] text-on-surface-variant/60 tracking-widest uppercase hover:text-on-surface transition-colors"
          >
            privacy
          </button>
          <button
            onClick={() => navigate('terms')}
            className="text-[10px] text-on-surface-variant/60 tracking-widest uppercase hover:text-on-surface transition-colors"
          >
            terms
          </button>
          <a
            href="https://souravsharan.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-on-surface-variant/60 tracking-widest uppercase hover:text-on-surface transition-colors"
          >
            built by sourav
          </a>
        </div>
      </footer>
    </div>
  )
}
