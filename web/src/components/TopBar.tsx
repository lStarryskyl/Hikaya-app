import Avatar from './Avatar'
import { t, useLocale, setLocale } from '../i18n'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Bell, LogOut, Plus, Search } from 'lucide-react'
import { useAuth } from '../auth'

export default function TopBar() {
  const locale = useLocale()

  const { user, loading, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [query, setQuery] = useState('')
  useEffect(() => setQuery(new URLSearchParams(location.search).get('q') ?? ''), [location.search])
  function search(event: FormEvent) {
    event.preventDefault()
    navigate(`/explore?${new URLSearchParams(query.trim() ? { q: query.trim() } : {})}`)
  }

  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b sm:flex-nowrap border-border bg-panel/95 px-4 py-3 backdrop-blur sm:px-6">
      <form
        role="search"
        onSubmit={search}
        className="order-2 mx-auto flex min-w-0 w-full max-w-5xl basis-full flex-1 sm:order-none sm:basis-auto items-center gap-2 rounded-full border border-border bg-[#F1EEE7] px-4 py-2.5"
      >
        <Search size={16} className="shrink-0 text-muted" />
        <input
          className="min-w-0 w-full bg-transparent text-sm outline-none placeholder:text-muted"
          aria-label={t('Search stories')}
          value={query}
          maxLength={200}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('Search stories, locations, or storytellers...')}
        />
      </form>
      <div className="ms-auto flex shrink-0 items-center gap-3">
        <button
          type="button"
          lang={locale === 'en' ? 'ar' : 'en'}
          aria-label={locale === 'en' ? 'Switch to Arabic' : 'التبديل إلى الإنجليزية'}
          onClick={() => setLocale(locale === 'en' ? 'ar' : 'en')}
          className="rounded-full border border-border px-3 py-2 text-sm"
        >
          {locale === 'en' ? 'العربية' : 'English'}
        </button>
        <Link
          to="/create"
          aria-label={t('Create story')}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
        >
          <Plus size={16} />
        </Link>
        <Link
          to="/notifications"
          aria-label={t('Notifications')}
          className="relative flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
        >
          <Bell size={16} />
          <span className="absolute end-2 top-1.5 h-1.5 w-1.5 rounded-full bg-terracotta" />
        </Link>
        {loading ? (
          <div className="h-8 w-24" aria-hidden />
        ) : user ? (
          <>
            <Link
              to="/profile"
              className="flex items-center gap-2 rounded-full py-0.5 pe-2 hover:bg-cream"
              aria-label={t('Open profile')}
            >
              <Avatar
                name={user.display_name}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-terracotta-light text-xs font-semibold text-terracotta-dark"
              />
              <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:inline">
                {user.display_name}
              </span>
            </Link>
            <button
              type="button"
              aria-label={t('Sign out')}
              title={t('Sign out')}
              onClick={() => void signOut()}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
            >
              <LogOut size={16} />
            </button>
          </>
        ) : (
          <Link
            to="/signin"
            className="rounded-full bg-terracotta px-4 py-2 text-sm font-medium text-cream hover:brightness-105"
          >
            {t('Sign in')}
          </Link>
        )}
      </div>
    </header>
  )
}
