import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="min-h-screen bg-background flex items-center justify-center px-8">
            <div className="text-center space-y-4">
              <h1 className="text-on-surface font-light text-xl">something went wrong</h1>
              <p className="text-on-surface-variant text-sm">
                try refreshing the page
              </p>
              <button
                onClick={() => window.location.reload()}
                className="text-primary text-sm hover:underline"
              >
                refresh
              </button>
            </div>
          </div>
        )
      )
    }

    return this.props.children
  }
}
