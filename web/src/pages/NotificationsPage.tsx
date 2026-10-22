import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Check, Heart, MapPin, MessageCircle, Mic, Trash2 } from 'lucide-react'
import { Card, PillButton } from '../components/ui'
import Photo from '../components/Photo'
import { findPhoto, getPlaces } from '../discover'
import { mockAvatarUrl } from '../demo/mockEngagement'
import { useApi } from '../useApi'

type NotifKind = 'like' | 'comment' | 'story' | 'map' | 'system'

interface Notification {
  id: string
  kind: NotifKind
  title: string
  body: string
  timeAgo: string
  unread: boolean
  href?: string
  avatarSeed?: string
  /** A place photo slug. */
  imageSeed?: string
}

const INITIAL: Notification[] = [
  {
    id: 'n1',
    kind: 'like',
    title: 'Layla Al-Sayed liked your story',
    body: 'Morning Steam in Old Al-Balad received a new like.',
    timeAgo: '12 min ago',
    unread: true,
    href: '/feed',
    avatarSeed: 'layla-al-sayed',
  },
  {
    id: 'n2',
    kind: 'comment',
    title: 'Omar Kassab commented',
    body: '“This brought the Oval Plaza back to life — thank you.”',
    timeAgo: '1 hour ago',
    unread: true,
    href: '/feed',
    avatarSeed: 'omar-kassab',
  },
  {
    id: 'n3',
    kind: 'story',
    title: 'New story near Madaba',
    body: 'The Loom of Ancestors was published in your followed region.',
    timeAgo: '3 hours ago',
    unread: true,
    href: '/feed',
    imageSeed: 'weaving-loom-2',
  },
  {
    id: 'n4',
    kind: 'map',
    title: 'Map pin confirmed',
    body: 'Your draft pin near Petra is ready to publish.',
    timeAgo: 'Yesterday',
    unread: false,
    href: '/create',
    imageSeed: 'petra-treasury',
  },
  {
    id: 'n5',
    kind: 'system',
    title: 'Archive reminder',
    body: 'Complete the transcript step to finish your contribution.',
    timeAgo: '2 days ago',
    unread: false,
    href: '/create',
  },
]

const iconFor: Record<NotifKind, typeof Heart> = {
  like: Heart,
  comment: MessageCircle,
  story: Mic,
  map: MapPin,
  system: Bell,
}

export default function NotificationsPage() {
  // Notifications are mock in the demo: this list lives only in the page.
  const [items, setItems] = useState(INITIAL)
  const places = useApi(getPlaces, [])
  const unread = items.filter((n) => n.unread).length

  function markAllRead() {
    setItems((prev) => prev.map((n) => ({ ...n, unread: false })))
  }

  function markRead(id: string) {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, unread: false } : n)))
  }

  function clearAll() {
    setItems([])
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl">Notifications</h1>
          <p className="text-sm text-muted">
            {unread > 0 ? `${unread} unread` : 'You’re all caught up'}
          </p>
        </div>
        <div className="flex gap-2">
          <PillButton variant="outline" className="!py-2 text-xs" onClick={markAllRead} disabled={!unread}>
            <Check size={13} /> Mark all read
          </PillButton>
          <PillButton variant="ghost" className="!py-2 text-xs" onClick={clearAll} disabled={items.length === 0}>
            <Trash2 size={13} /> Clear
          </PillButton>
        </div>
      </div>

      {items.length === 0 ? (
        <Card className="px-6 py-16 text-center">
          <Bell size={28} className="mx-auto mb-3 text-muted" />
          <p className="font-serif text-lg">No notifications</p>
          <p className="mt-1 text-sm text-muted">Likes, comments, and nearby stories will show up here.</p>
          <Link to="/feed" className="mt-4 inline-block text-sm font-medium text-terracotta">
            Browse the feed
          </Link>
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((n) => {
            const Icon = iconFor[n.kind]
            const inner = (
              <Card
                className={`flex gap-3 p-3.5 transition hover:shadow-sm ${
                  n.unread ? 'border-terracotta/30 bg-terracotta-light/20' : ''
                }`}
              >
                {n.avatarSeed ? (
                  <img
                    src={mockAvatarUrl(n.avatarSeed, 80)}
                    alt=""
                    className="h-11 w-11 shrink-0 rounded-full object-cover"
                  />
                ) : n.imageSeed ? (
                  <Photo
                    photo={findPhoto(places.data, n.imageSeed)}
                    width={88}
                    className="h-11 w-11 shrink-0 rounded-lg object-cover"
                  />
                ) : (
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-cream text-terracotta">
                    <Icon size={18} />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold text-ink">{n.title}</p>
                    {n.unread && (
                      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-terracotta" />
                    )}
                  </div>
                  <p className="mt-0.5 text-[13px] leading-snug text-muted2">{n.body}</p>
                  <p className="mt-1.5 text-[11px] text-muted">{n.timeAgo}</p>
                </div>
              </Card>
            )

            if (n.href) {
              return (
                <Link
                  key={n.id}
                  to={n.href}
                  className="block no-underline"
                  onClick={() => markRead(n.id)}
                >
                  {inner}
                </Link>
              )
            }
            return (
              <button
                key={n.id}
                type="button"
                className="block w-full text-left"
                onClick={() => markRead(n.id)}
              >
                {inner}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
