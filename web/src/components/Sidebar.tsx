import { NavLink } from 'react-router-dom'
import { BookOpen, Home, Map, PlusCircle, Rss } from 'lucide-react'

const navItems = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/explore', label: 'Explore Map', icon: Map },
  { to: '/create', label: 'Create Story', icon: PlusCircle },
  { to: '/feed', label: 'Social Feed', icon: Rss },
]

export default function Sidebar() {
  return (
    <aside className="hidden w-[232px] shrink-0 flex-col justify-between border-r border-border bg-panel px-4 py-5 md:flex">
      <div>
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-terracotta text-cream shadow-sm">
            <BookOpen size={18} strokeWidth={1.75} />
          </div>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">Hikaya</div>
            <div className="font-arabic text-[11px] text-muted">حكاية</div>
          </div>
        </div>

        <nav className="flex flex-col gap-1">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 rounded-full px-3 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'bg-[#EFEBE3] font-semibold text-ink'
                    : 'text-muted2 hover:bg-cream/80',
                ].join(' ')
              }
            >
              <Icon size={17} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div
        className="px-2 text-[10px] uppercase tracking-[0.18em] text-muted"
        style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', height: '9rem' }}
      >
        Heritage Preservation
      </div>
    </aside>
  )
}
