import { ChatDemo } from './ChatDemo'
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
          <p className="landing-subtitle">you don't organize anything. you just talk.</p>
        </header>

        <div className="landing-demo-section">
          <ChatDemo onSignIn={onGetStarted} />
        </div>

        <p className="landing-signin-link">
          already have an account?{' '}
          <button className="landing-signin-btn" type="button" onClick={onGetStarted}>
            sign in
          </button>
        </p>

        <div className="landing-taglines">
          <p className="landing-tagline">no lists. no dashboards. nothing to maintain. ever.</p>
        </div>

        <p className="landing-pricing">free · $8/mo unlimited</p>

        <footer className="landing-footer">
          <a href="/privacy" className="landing-footer-link">
            privacy
          </a>
          <span className="landing-footer-sep">·</span>
          <a href="/terms" className="landing-footer-link">
            terms
          </a>
        </footer>
      </div>

      <svg
        className="landing-hills"
        viewBox="0 0 1440 400"
        preserveAspectRatio="xMidYMax slice"
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
      </svg>
    </div>
  )
}
