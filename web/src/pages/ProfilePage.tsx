import { Link } from 'react-router-dom'
import {
  Bookmark,
  Camera,
  Heart,
  MapPin,
  MessageCircle,
  Settings,
  Share2,
} from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import Photo from '../components/Photo'
import { initials, useAuth } from '../auth'
import { findPhoto, getFeed, getPlaces } from '../discover'
import { engagementFor } from '../demo/mockEngagement'
import { formatDuration } from '../stories'
import { useApi } from '../useApi'

export default function ProfilePage() {
  const { user } = useAuth()
  const feed = useApi(() => getFeed({ limit: 100 }), [])
  const places = useApi(getPlaces, [])
  const stories = feed.data?.items ?? []
  // Published stories only; drafts and stories under review get their own list in #10.
  const myStories = stories.filter((s) => s.author.id === user?.id)
  // Saving is mock in the demo: these are examples, not stored choices.
  const saved = stories.filter((s) => s.author.id !== user?.id).slice(0, 4)
  const banner = findPhoto(places.data, 'amman-citadel')

  if (!user) {
    return (
      <div className="mx-auto max-w-md p-12 text-center">
        <h1 className="mb-2 font-serif text-2xl">Your profile</h1>
        <p className="mb-6 text-sm text-muted2">Sign in to see your stories.</p>
        <Link to="/signin?next=%2Fprofile" className="text-sm font-medium text-terracotta hover:underline">
          Sign in
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl">Profile</h1>
          <p className="text-sm text-muted">Your archive identity on Hikaya</p>
        </div>
        <Link to="/settings">
          <PillButton variant="outline" className="!py-2 text-xs">
            <Settings size={14} /> Settings
          </PillButton>
        </Link>
      </div>

      <Card className="overflow-hidden">
        <div className="relative h-36 sm:h-44">
          <Photo photo={banner} width={1400} sizes="(min-width: 896px) 896px, 100vw" className="h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
        </div>
        <div className="relative px-5 pb-5 pt-0 sm:px-6">
          <div className="-mt-12 mb-4 flex flex-wrap items-end gap-4">
            <div className="relative">
              <span className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-panel bg-terracotta-light font-serif text-2xl text-terracotta-dark shadow">
                {initials(user.display_name)}
              </span>
              <button
                type="button"
                className="absolute bottom-1 right-1 flex h-8 w-8 items-center justify-center rounded-full bg-terracotta text-cream shadow"
                aria-label="Change photo"
              >
                <Camera size={14} />
              </button>
            </div>
            <div className="mb-1 flex-1">
              <h2 className="font-serif text-xl">{user.display_name}</h2>
              <p className="text-sm text-muted">{user.email}</p>
            </div>
            <PillButton variant="primary" className="!py-2 text-xs">
              Edit profile
            </PillButton>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <Badge tone="terracotta">Storyteller</Badge>
            {user.role !== 'member' && <Badge tone="teal">{user.role === 'admin' ? 'Admin' : 'Reviewer'}</Badge>}
          </div>

          <div className="grid grid-cols-3 gap-3 sm:max-w-md">
            {[
              { label: 'Published', value: feed.data ? myStories.length : '…' },
              { label: 'Saved', value: saved.length },
              { label: 'Following', value: 0 },
            ].map((s) => (
              <div key={s.label} className="rounded-xl bg-cream px-3 py-3 text-center">
                <div className="font-serif text-lg">{s.value}</div>
                <div className="text-[11px] text-muted">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-serif text-lg">My stories</h3>
          <Link to="/create" className="text-xs font-medium text-terracotta">
            Record new
          </Link>
        </div>
        {feed.data && myStories.length === 0 && (
          <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted2">
            You have not published a story yet.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {myStories.map((s) => (
            <Link key={s.id} to={`/story/${s.id}`} className="no-underline">
              <Card className="overflow-hidden transition hover:shadow-md">
                <Photo photo={s.cover} width={600} sizes="(min-width: 640px) 50vw, 100vw" className="h-36 w-full object-cover" />
                <div className="p-3">
                  <div className="mb-1 flex items-center gap-1 text-[11px] text-muted">
                    <MapPin size={11} /> {s.place_name}
                  </div>
                  <div className="font-serif text-[15px] text-ink">{s.title}</div>
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-muted">
                    <span className="inline-flex items-center gap-1">
                      <Heart size={11} /> {engagementFor(s.id).likes}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <MessageCircle size={11} /> {engagementFor(s.id).comments}
                    </span>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <Bookmark size={16} className="text-terracotta" />
          <h3 className="font-serif text-lg">Saved for later</h3>
          <span className="text-[11px] text-muted">(examples)</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {saved.map((s) => (
            <Link
              key={s.id}
              to={`/story/${s.id}`}
              className="flex gap-3 rounded-xl border border-border bg-panel p-2.5 no-underline transition hover:bg-cream"
            >
              <Photo photo={s.cover} width={128} className="h-16 w-16 shrink-0 rounded-lg object-cover" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-ink">{s.title}</div>
                <div className="text-[11px] text-muted">
                  {s.place_name} · {formatDuration(s.duration_ms)}
                </div>
              </div>
              <Share2 size={14} className="mt-1 text-muted" />
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
