import { t, useLocale } from '../i18n'
import { FormEvent, ReactNode, useState } from 'react'
import { BookOpen } from 'lucide-react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Card, PillButton } from '../components/ui'

const inputClass =
  'mt-1 w-full rounded-lg border border-border bg-cream px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-terracotta/30'

// Only follow paths inside this site, never a full URL someone put in the link.
function safeNext(raw: string | null): string {
  return raw && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/'
}

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  useLocale()

  return (
    <div className="flex min-h-screen items-center justify-center bg-cream px-4 py-10 font-sans text-ink">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-terracotta text-cream shadow-sm">
            <BookOpen size={20} strokeWidth={1.75} />
          </div>
          <div className="text-start leading-tight">
            <div className="text-base font-semibold tracking-tight">{t('Hikaya')}</div>
            <div className="font-arabic text-xs text-muted">حكاية</div>
          </div>
        </Link>
        <Card className="p-7">
          <h1 className="font-serif text-2xl font-medium">{t(title)}</h1>
          <p className="mt-1 text-sm text-muted2">{t(subtitle)}</p>
          <div className="mt-6">{t(children)}</div>
        </Card>
      </div>
    </div>
  )
}

function ErrorLine({ message }: { message: string }) {
  useLocale()

  if (!message) return null
  return (
    <p
      role="alert"
      className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
    >
      {t(message)}
    </p>
  )
}

export function SignInPage() {
  useLocale()

  const { user, signIn } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={next} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await signIn(email, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Could not sign in.'))
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title={t('Welcome back')}
      subtitle="Sign in to share and keep stories from your community."
    >
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Email')}
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Password')}
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </label>
        <ErrorLine message={t(error)} />
        <PillButton
          type="submit"
          disabled={busy}
          className="w-full justify-center disabled:opacity-60"
        >
          {busy ? t('Signing in…') : t('Sign in')}
        </PillButton>
      </form>
      <p className="mt-5 text-center text-sm text-muted2">
        {t('New to Hikaya?')}{' '}
        <Link
          to={`/signup${next === '/' ? '' : `?next=${encodeURIComponent(next)}`}`}
          className="font-medium text-terracotta hover:underline"
        >
          {t('Create an account')}
        </Link>
      </p>
    </AuthShell>
  )
}

export function SignUpPage() {
  useLocale()

  const { user, signUp } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={next} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await signUp(email, password, displayName)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Could not create the account.'))
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title={t('Join Hikaya')}
      subtitle="Record a story once, and let it be heard for generations."
    >
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Your name')}
          <input
            required
            maxLength={60}
            autoComplete="name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Email')}
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Password')}
          <input
            type="password"
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            aria-label={t('Password')}
            aria-describedby="signup-password-hint"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
          <span id="signup-password-hint" className="mt-1 block text-[11px] text-muted">
            {t('At least 8 characters.')}
          </span>
        </label>
        <ErrorLine message={t(error)} />
        <PillButton
          type="submit"
          disabled={busy}
          className="w-full justify-center disabled:opacity-60"
        >
          {busy ? t('Creating account…') : t('Create account')}
        </PillButton>
      </form>
      <p className="mt-5 text-center text-sm text-muted2">
        {t('Already have an account?')}{' '}
        <Link
          to={`/signin${next === '/' ? '' : `?next=${encodeURIComponent(next)}`}`}
          className="font-medium text-terracotta hover:underline"
        >
          {t('Sign in')}
        </Link>
      </p>
    </AuthShell>
  )
}
