import './LandingPage.css'

interface LandingPageProps {
  onGetStarted: () => void
}

export function LandingPage({ onGetStarted }: LandingPageProps) {
  return (
    <div className="landing">
      <div className="stars">
        <div className="stars-small" />
        <div className="stars-medium" />
        <div className="stars-large" />
      </div>

      <div className="landing-content">
        <header className="landing-hero">
          <h1 className="landing-title">unspool</h1>
          <p className="landing-subtitle">
            an AI that remembers everything so you don't have to
          </p>
        </header>

        <div className="landing-pitch">
          <p className="landing-line">no lists. no dashboards. no organizing.</p>
          <p className="landing-line">just tell me what's on your mind.</p>
        </div>

        <div className="landing-features">
          <div className="landing-feature">
            <span className="landing-feature-label">dump everything</span>
            <span className="landing-feature-desc">tasks, ideas, deadlines, random thoughts — just type</span>
          </div>
          <div className="landing-feature">
            <span className="landing-feature-label">ask what's next</span>
            <span className="landing-feature-desc">one thing at a time, when you're ready</span>
          </div>
          <div className="landing-feature">
            <span className="landing-feature-label">nothing falls through</span>
            <span className="landing-feature-desc">it all fades in and out at the right moment</span>
          </div>
        </div>

        <button
          className="landing-cta"
          type="button"
          onClick={onGetStarted}
        >
          get started — it's free
        </button>

        <p className="landing-pricing">
          free up to 10 messages a day. unlimited for $8/mo.
        </p>

        <footer className="landing-footer">
          <a href="/privacy" className="landing-footer-link">privacy</a>
          <span className="landing-footer-sep">·</span>
          <a href="/terms" className="landing-footer-link">terms</a>
        </footer>
      </div>

      <svg
        className="landing-hills"
        viewBox="0 0 1440 400"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M0 300 Q200 220 400 270 Q600 320 800 250 Q1000 180 1200 230 Q1400 280 1440 260 L1440 400 L0 400 Z"
          fill="rgba(0,0,0,0.3)"
        />
        <path
          d="M0 340 Q250 280 500 320 Q750 360 1000 300 Q1200 250 1440 310 L1440 400 L0 400 Z"
          fill="rgba(0,0,0,0.5)"
        />
        <path
          d="M0 370 Q300 330 600 360 Q900 390 1200 350 Q1350 340 1440 365 L1440 400 L0 400 Z"
          fill="rgba(0,0,0,0.7)"
        />
        {/* Cat silhouette */}
        <g transform="translate(920, 210)">
          <ellipse cx="0" cy="12" rx="7" ry="10" fill="rgba(0,0,0,0.5)" />
          <circle cx="0" cy="-2" r="6" fill="rgba(0,0,0,0.5)" />
          <polygon points="-5,-6 -2,-13 0,-5" fill="rgba(0,0,0,0.5)" />
          <polygon points="5,-6 2,-13 0,-5" fill="rgba(0,0,0,0.5)" />
          <path
            d="M6 13 Q15 7 17 -1 Q18 -4 15 -3"
            fill="none"
            stroke="rgba(0,0,0,0.5)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </g>
      </svg>
    </div>
  )
}
