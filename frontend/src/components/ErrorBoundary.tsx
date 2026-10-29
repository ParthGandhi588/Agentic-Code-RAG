import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            height: '100vh',
            width: '100vw',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#0e0e11',
            color: '#e4e4e7',
            padding: 24,
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          <div
            style={{
              maxWidth: 480,
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 12,
              padding: 24,
              textAlign: 'center',
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <AlertTriangle size={42} style={{ color: '#ef4444' }} />
            </div>
            <h2 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#fff', marginBottom: 8 }}>
              Interface Recovered
            </h2>
            <p style={{ fontSize: '0.85rem', color: '#a1a1aa', marginBottom: 20, lineHeight: 1.5 }}>
              {this.state.error?.message || 'A component error occurred. Click below to reset.'}
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  background: 'var(--accent-primary, #f97316)',
                  color: '#000',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  border: 'none',
                  borderRadius: 8,
                  padding: '9px 18px',
                  cursor: 'pointer',
                }}
              >
                <RefreshCw size={15} />
                <span>Dismiss & Continue</span>
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
