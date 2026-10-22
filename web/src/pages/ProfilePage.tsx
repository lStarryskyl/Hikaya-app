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
import { stories, imageUrl, avatarUrl } from '../data/mock'

const saved = stories.slice(0, 4)
const myStories = stories.filter((s) =>
  ['loom-of-ancestors', 'morning-steam'].includes(s.id),
)

export default function ProfilePage() {
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
          <img
            src={imageUrl('amman-citadel', 1400, 400)}
            alt=""
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
        </div>
        <div className="relative px-5 pb-5 pt-0 sm:px-6">
          <div className="-mt-12 mb-4 flex flex-wrap items-end gap-4">
            <div className="relative">
              <img
                src={avatarUrl('salma-k', 160)}
                alt=""
                className="h-24 w-24 rounded-full border-4 border-panel object-cover shadow"
              />
              <button
                type="button"
                className="absolute bottom-1 right-1 flex h-8 w-8 items-center justify-center rounded-full bg-terracotta text-cream shadow"
                aria-label="Change photo"
              >
                <Camera size={14} />
              </button>
            </div>
            <div className="mb-1 flex-1">
              <h2 className="font-serif text-xl">Salma Khalil</h2>
              <p className="text-sm text-muted">@salma_k · Amman, Jordan</p>
            </div>
            <PillButton variant="primary" className="!py-2 text-xs">
              Edit profile
            </PillButton>
          </div>

          <p className="mb-4 max-w-2xl text-sm leading-relaxed text-muted2">
            Field collector and oral-history enthusiast. Documenting family recipes, neighborhood
            walks, and elders’ memories across the Kingdom.
          </p>

          <div className="mb-4 flex flex-wrap gap-2">
            <Badge tone="terracotta">Storyteller</Badge>
            <Badge tone="teal">Field collector</Badge>
            <Badge tone="gold">Amman</Badge>
          </div>

          <div className="grid grid-cols-3 gap-3 sm:max-w-md">
            {[
              { label: 'Stories', value: '12' },
              { label: 'Saved', value: '48' },
              { label: 'Following', value: '86' },
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
        <div className="grid gap-4 sm:grid-cols-2">
          {myStories.map((s) => (
            <Link key={s.id} to={`/story/${s.id}`} className="no-underline">
              <Card className="overflow-hidden transition hover:shadow-md">
                <img
                  src={imageUrl(s.imageSeed, 600, 360)}
                  alt=""
                  className="h-36 w-full object-cover"
                />
                <div className="p-3">
                  <div className="mb-1 flex items-center gap-1 text-[11px] text-muted">
                    <MapPin size={11} /> {s.place}
                  </div>
                  <div className="font-serif text-[15px] text-ink">{s.title}</div>
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-muted">
                    <span className="inline-flex items-center gap-1">
                      <Heart size={11} /> {s.likes}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <MessageCircle size={11} /> {s.comments}
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
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {saved.map((s) => (
            <Link
              key={s.id}
              to={`/story/${s.id}`}
              className="flex gap-3 rounded-xl border border-border bg-panel p-2.5 no-underline transition hover:bg-cream"
            >
              <img
                src={imageUrl(s.imageSeed, 160, 160)}
                alt=""
                className="h-16 w-16 rounded-lg object-cover"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-ink">{s.title}</div>
                <div className="text-[11px] text-muted">
                  {s.place} · {s.duration}
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
