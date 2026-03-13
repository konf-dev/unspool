import { useState, useEffect } from 'react'
import type { Message } from './types'
import { fetchMessages } from './lib/api'
import { useAuth } from './hooks/useAuth'
import { LoginScreen } from './components/LoginScreen'
import { ChatScreen } from './components/ChatScreen'

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content:
    "hey, i'm unspool. just type whatever's on your mind — tasks, ideas, deadlines, random thoughts. i'll keep track of everything so you don't have to.",
  createdAt: new Date().toISOString(),
  actions: [
    { label: 'suggest something', value: 'what should I do?' },
    { label: 'just dumping', value: "brain dump time" },
  ],
}

export function App() {
  const { isAuthenticated, isLoading, userId, token, signInWithGoogle, signInWithEmail, signOut } =
    useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [fadeClass, setFadeClass] = useState('app-screen')
  const [prevAuth, setPrevAuth] = useState<boolean | null>(null)

  useEffect(() => {
    if (isLoading) return

    if (isAuthenticated && token) {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 10000)

      void fetchMessages(token, 50)
        .then((fetched) => {
          setMessages(fetched.length > 0 ? fetched : [WELCOME_MESSAGE])
        })
        .catch(() => {
          setMessages([WELCOME_MESSAGE])
        })
        .finally(() => clearTimeout(timeout))

      return () => {
        clearTimeout(timeout)
        controller.abort()
      }
    }
  }, [isAuthenticated, isLoading, token])

  useEffect(() => {
    if (isLoading) return

    if (prevAuth === null) {
      setFadeClass('app-screen visible')
      setPrevAuth(isAuthenticated)
      return
    }

    if (prevAuth !== isAuthenticated) {
      setFadeClass('app-screen')
      const timer = setTimeout(() => {
        setPrevAuth(isAuthenticated)
        setFadeClass('app-screen visible')
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [isAuthenticated, isLoading, prevAuth])

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
    <div className={fadeClass}>
      {!isAuthenticated ? (
        <LoginScreen
          onSignInWithGoogle={signInWithGoogle}
          onSignInWithEmail={signInWithEmail}
        />
      ) : (
        <ChatScreen
          initialMessages={messages}
          token={token ?? ''}
          userId={userId ?? ''}
          onSignOut={signOut}
        />
      )}
    </div>
  )
}
