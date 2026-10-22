import { Link } from 'react-router-dom'
import { Bell, Plus, Search } from 'lucide-react'
import { avatarUrl } from '../data/mock'

export default function TopBar() {
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
        <Link
          to="/profile"
          className="flex items-center gap-2 rounded-full py-0.5 pe-2 hover:bg-cream"
          aria-label="Open profile"
        >
          <img
            src={avatarUrl('salma-k', 60)}
            alt=""
            className="h-8 w-8 rounded-full object-cover"
          />
          <span className="hidden text-sm font-medium sm:inline">Salma K.</span>
        </Link>
      </div>
    </header>
  )
}
