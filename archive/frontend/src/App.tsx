import { useState, useEffect, useCallback } from 'react'
import type { Message } from './types'
import { fetchMessages } from './lib/api'
import { useAuth } from './hooks/useAuth'
import { UIModeProvider } from './contexts/UIMode'
import { LandingPage } from './components/LandingPage'
import { LoginScreen } from './components/LoginScreen'
import { ChatScreen } from './components/ChatScreen'
import { PrivacyPage, TermsPage } from './components/LegalPage'

type Route = 'landing' | 'login' | 'chat' | 'privacy' | 'terms'

function isStandalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean }
  return nav.standalone === true || window.matchMedia('(display-mode: standalone)').matches
}

function getInitialRoute(): Route {
  const path = window.location.pathname
  if (path === '/privacy') return 'privacy'
  if (path === '/terms') return 'terms'
  if (path === '/login') return 'login'
  if (path === '/chat') return 'chat'
  // PWA standalone mode: skip landing, go straight to login/chat
  if (isStandalone()) return 'login'
  return 'landing'
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: 'hey — dump anything on me. tasks, ideas, deadlines, random thoughts. i sort it out.',
  createdAt: new Date().toISOString(),
  actions: [
    { label: 'what should I do?', value: 'what should I do?' },
    { label: 'just dumping', value: 'brain dump time' },
  ],
}

export function App() {
  const { isAuthenticated, isLoading, userId, token, signInWithGoogle, signInWithEmail, signOut } =
    useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [route, setRoute] = useState<Route>(getInitialRoute)
  const [fadeClass, setFadeClass] = useState('app-screen')
  const [prevScreen, setPrevScreen] = useState<string | null>(null)

  // Navigate helper — updates URL and state
  const navigate = useCallback((to: Route) => {
    const path = to === 'landing' ? '/' : `/${to}`
    window.history.pushState(null, '', path)
    setRoute(to)
  }, [])

  // Handle browser back/forward
  useEffect(() => {
    const handlePop = () => {
      const path = window.location.pathname
      if (path === '/privacy') setRoute('privacy')
      else if (path === '/terms') setRoute('terms')
      else if (path === '/login') setRoute('login')
      else setRoute(isAuthenticated ? 'chat' : 'landing')
    }
    window.addEventListener('popstate', handlePop)
    return () => window.removeEventListener('popstate', handlePop)
  }, [isAuthenticated])

  // When auth resolves, redirect to chat if authenticated
  useEffect(() => {
    if (isLoading) return

    if (isAuthenticated) {
      // Authenticated: go to chat (unless on a legal page or already there)
      if (route !== 'privacy' && route !== 'terms' && route !== 'chat') {
        setRoute('chat')
        window.history.replaceState(null, '', '/chat')
      }
    } else if (route === 'chat') {
      // Not authenticated but on chat: go to login
      setRoute('login')
      window.history.replaceState(null, '', '/login')
    }
  }, [isAuthenticated, isLoading, route])

  // Fetch messages when entering chat + handle demo-to-auth bridge
  useEffect(() => {
    if (isLoading || !isAuthenticated || route !== 'chat') return

    // Clear demo conversation from localStorage (fresh start after sign-in)
    localStorage.removeItem('unspool-demo-messages')
    localStorage.removeItem('unspool-demo-count')

    if (!token) {
      // Token not ready yet — show welcome message, will re-run when token arrives
      setMessages([WELCOME_MESSAGE])
      return
    }

    void fetchMessages(token, 50)
      .then((fetched) => {
        setMessages(fetched.length > 0 ? fetched : [WELCOME_MESSAGE])
      })
      .catch(() => {
        setMessages([WELCOME_MESSAGE])
      })
  }, [isAuthenticated, isLoading, token, route])

  // Fade transition on screen changes
  const currentScreen = `${route}-${isAuthenticated}`
  useEffect(() => {
    if (isLoading) return

    if (prevScreen === null) {
      setFadeClass('app-screen visible')
      setPrevScreen(currentScreen)
      return
    }

    if (prevScreen !== currentScreen) {
      const doc = document as Document & {
        startViewTransition?: (cb: () => void) => void
      }

      if (doc.startViewTransition) {
        doc.startViewTransition(() => {
          setPrevScreen(currentScreen)
        })
        setFadeClass('app-screen visible')
      } else {
        setFadeClass('app-screen')
        const timer = setTimeout(() => {
          setPrevScreen(currentScreen)
          setFadeClass('app-screen visible')
        }, 300)
        return () => clearTimeout(timer)
      }
    }
  }, [currentScreen, isLoading, prevScreen])

  const handleGetStarted = useCallback(() => {
    navigate('login')
  }, [navigate])

  const handleBackToLanding = useCallback(() => {
    if (window.history.length > 1) {
      window.history.back()
    } else {
      navigate('landing')
    }
  }, [navigate])

  if (isLoading) {
    return (
      <div className="app-screen visible">
        <div className="loading-screen">
          <div className="stars">
            <div className="stars-small" />
            <div className="stars-medium" />
            <div className="stars-large" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <UIModeProvider>
      <div className={fadeClass}>
        {route === 'privacy' && <PrivacyPage onBack={handleBackToLanding} />}
        {route === 'terms' && <TermsPage onBack={handleBackToLanding} />}
        {route === 'landing' && <LandingPage onGetStarted={handleGetStarted} />}
        {route === 'login' && (
          <LoginScreen onSignInWithGoogle={signInWithGoogle} onSignInWithEmail={signInWithEmail} />
        )}
        {route === 'chat' && (
          <ChatScreen
            initialMessages={messages}
            token={token ?? ''}
            userId={userId ?? ''}
            onSignOut={signOut}
          />
        )}
      </div>
    </UIModeProvider>
  )
}
