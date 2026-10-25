import { Component, type ReactNode } from 'react'
import { t } from '../i18n'
export default class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: Error) {
    console.error('View failed:', error.message)
  }
  render() {
    if (this.state.failed)
      return (
        this.props.fallback ?? (
          <div role="alert" className="p-8">
            <p>{t('Something went wrong')}</p>
            <button
              type="button"
              className="mt-3 underline"
              onClick={() => window.location.reload()}
            >
              {t('Try again')}
            </button>
          </div>
        )
      )
    return this.props.children
  }
}
