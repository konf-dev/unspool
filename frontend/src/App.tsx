import { useEffect, lazy, Suspense } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from '@/hooks/useAuth'
import { useUIStore } from '@/stores/uiStore'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { LoadingScreen } from '@/components/system/LoadingScreen'
import { ErrorBoundary } from '@/components/system/ErrorBoundary'

const LandingPage = lazy(() =>
  import('@/components/landing/LandingPage').then((m) => ({ default: m.LandingPage })),
)
const LoginScreen = lazy(() =>
  import('@/components/auth/LoginScreen').then((m) => ({ default: m.LoginScreen })),
)
const StreamPage = lazy(() =>
  import('@/components/stream/StreamPage').then((m) => ({ default: m.StreamPage })),
)
const PrivacyPage = lazy(() =>
  import('@/components/legal/PrivacyPage').then((m) => ({ default: m.PrivacyPage })),
)
const TermsPage = lazy(() =>
  import('@/components/legal/TermsPage').then((m) => ({ default: m.TermsPage })),
)

const pageTransition = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.3, ease: 'easeInOut' },
}

export function App() {
  const { isAuthenticated, isLoading } = useAuth()
  const route = useUIStore((s) => s.route)
  const reduced = useReducedMotion()

  useEffect(() => {
    const cleanup = useUIStore.getState()._initRoute()
    return cleanup
  }, [])

  // Auth-based routing
  useEffect(() => {
    if (isLoading) return

    const { navigate } = useUIStore.getState()

    if (isAuthenticated && (route === 'login' || route === 'landing')) {
      navigate('chat')
    } else if (!isAuthenticated && route === 'chat') {
      navigate('login')
    }

    // PWA standalone: skip landing, go to login
    if (
      !isAuthenticated &&
      route === 'landing' &&
      window.matchMedia('(display-mode: standalone)').matches
    ) {
      navigate('login')
    }
  }, [isAuthenticated, isLoading, route])

  if (isLoading) {
    return <LoadingScreen />
  }

  const renderPage = () => {
    switch (route) {
      case 'landing':
        return <LandingPage />
      case 'login':
        return <LoginScreen />
      case 'chat':
        return <StreamPage />
      case 'privacy':
        return <PrivacyPage />
      case 'terms':
        return <TermsPage />
      default:
        return <LandingPage />
    }
  }

  const motionProps = reduced ? {} : pageTransition

  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingScreen />}>
        <AnimatePresence mode="wait">
          <motion.div key={route} {...motionProps} className="min-h-screen">
            {renderPage()}
          </motion.div>
        </AnimatePresence>
      </Suspense>
    </ErrorBoundary>
  )
}
