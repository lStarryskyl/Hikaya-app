import { Link } from 'react-router-dom'
import { Bell, LogOut, Plus, Search } from 'lucide-react'
import { initials, useAuth } from '../auth'

export default function TopBar() {
  const { user, loading, signOut } = useAuth()

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-border bg-panel/95 px-4 py-3 backdrop-blur sm:px-6">
      <div className="mx-auto flex w-full max-w-5xl flex-1 items-center gap-2 rounded-full border border-border bg-[#F1EEE7] px-4 py-2.5">
        <Search size={16} className="shrink-0 text-muted" />
        <input
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
          placeholder="Search stories, locations, or storytellers..."
        />
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Link
          to="/create"
          aria-label="Create story"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
        >
          <Plus size={16} />
        </Link>
        <Link
          to="/notifications"
          aria-label="Notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
        >
          <Bell size={16} />
          <span className="absolute right-2 top-1.5 h-1.5 w-1.5 rounded-full bg-terracotta" />
        </Link>
        {loading ? (
          <div className="h-8 w-24" aria-hidden />
        ) : user ? (
          <>
            <Link
              to="/profile"
              className="flex items-center gap-2 rounded-full py-0.5 pe-2 hover:bg-cream"
              aria-label="Open profile"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-terracotta-light text-xs font-semibold text-terracotta-dark">
                {initials(user.display_name)}
              </span>
              <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:inline">
                {user.display_name}
              </span>
            </Link>
            <button
              type="button"
              aria-label="Sign out"
              title="Sign out"
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
            Sign in
          </Link>
        )}
      </div>
    </header>
  )
}
