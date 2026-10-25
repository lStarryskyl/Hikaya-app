import Avatar from '../components/Avatar'
import { t, useLocale } from '../i18n'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bookmark, Camera, MapPin, Settings, Share2 } from 'lucide-react'
import { Badge, Card, PillButton, PillLink } from '../components/ui'
import Photo from '../components/Photo'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { findPhoto, getFeed, getPlaces } from '../discover'
import {
  MODERATION_LABELS,
  STATUS_LABELS,
  deleteStory,
  formatDuration,
  getMyStories,
  type StoryStatus,
} from '../stories'
import { useApi } from '../useApi'

const STATUS_TONE: Record<StoryStatus, 'terracotta' | 'gold' | 'teal'> = {
  draft: 'gold',
  moderating: 'gold',
  published: 'teal',
  held: 'terracotta',
  needs_edit: 'terracotta',
}

export default function ProfilePage() {
  useLocale()

  const { user } = useAuth()
  const feed = useApi(() => getFeed({ limit: 100 }), [])
  const places = useApi(getPlaces, [])
  const stories = feed.data?.items ?? []
  const [refresh, setRefresh] = useState(0)
  // Signed-out visitors are asked to sign in instead, so their list is never requested.
  const mine = useApi(() => (user ? getMyStories() : Promise.resolve([])), [refresh, user?.id])
  const [confirming, setConfirming] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const published = (mine.data ?? []).filter((s) => s.status === 'published').length

  // Deleting asks twice on the same button, so nothing is removed by a single slip. The
  // second click must come within a few seconds; after that the button asks again.
  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(null), 4000)
    return () => window.clearTimeout(timer)
  }, [confirming])

  async function remove(id: string) {
    if (confirming !== id) {
      setConfirming(id)
      return
    }
    setDeleting(id)
    setDeleteError('')
    try {
      await deleteStory(id)
      setRefresh((n) => n + 1)
    } catch (e) {
      setDeleteError(
        e instanceof ApiError ? e.message : t('The story could not be deleted. Please try again.'),
      )
    } finally {
      setDeleting(null)
      setConfirming(null)
    }
  }
  // Saving is mock in the demo: these are examples, not stored choices.
  const saved = stories.filter((s) => s.author.id !== user?.id).slice(0, 4)
  const banner = findPhoto(places.data, 'amman-citadel')

  if (!user) {
    return (
      <div className="mx-auto max-w-md p-12 text-center">
        <h1 className="mb-2 font-serif text-2xl">{t('Your profile')}</h1>
        <p className="mb-6 text-sm text-muted2">{t('Sign in to see your stories.')}</p>
        <Link
          to="/signin?next=%2Fprofile"
          className="text-sm font-medium text-terracotta hover:underline"
        >
          {t('Sign in')}
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl">{t('Profile')}</h1>
          <p className="text-sm text-muted">{t('Your archive identity on Hikaya')}</p>
        </div>
        <PillLink to="/settings" variant="outline" className="!py-2 text-xs">
          <Settings size={14} /> {t('Settings')}
        </PillLink>
      </div>

      <Card className="overflow-hidden">
        <div className="relative h-36 sm:h-44">
          <Photo
            photo={banner}
            width={1400}
            sizes="(min-width: 896px) 896px, 100vw"
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
        </div>
        <div className="relative px-5 pb-5 pt-0 sm:px-6">
          <div className="-mt-12 mb-4 flex flex-wrap items-end gap-4">
            <div className="relative">
              <Avatar
                name={user.display_name}
                className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-panel bg-terracotta-light font-serif text-2xl text-terracotta-dark shadow"
              />
              <button
                type="button"
                className="absolute bottom-1 end-1 flex h-8 w-8 items-center justify-center rounded-full bg-terracotta text-cream shadow"
                aria-label={t('Change photo')}
              >
                <Camera size={14} />
              </button>
            </div>
            <div className="mb-1 flex-1">
              <h2 className="font-serif text-xl">{user.display_name}</h2>
              <p className="text-sm text-muted">{user.email}</p>
            </div>
            <PillButton variant="primary" className="!py-2 text-xs">
              {t('Edit profile')}
            </PillButton>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <Badge tone="terracotta">{t('Storyteller')}</Badge>
            {user.role !== 'member' && (
              <Badge tone="teal">{user.role === 'admin' ? t('Admin') : t('Reviewer')}</Badge>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3 sm:max-w-md">
            {[
              { label: 'Published', value: mine.data ? published : '…' },
              { label: 'Saved', value: saved.length },
              { label: 'Following', value: 0 },
            ].map((s) => (
              <div key={t(s.label)} className="rounded-xl bg-cream px-3 py-3 text-center">
                <div className="font-serif text-lg">{t(s.value)}</div>
                <div className="text-[11px] text-muted">{t(s.label)}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-serif text-lg">{t('My stories')}</h3>
          <Link to="/create" className="text-xs font-medium text-terracotta">
            {t('Record new')}
          </Link>
        </div>
        {mine.error && <p className="text-sm text-terracotta-dark">{mine.error}</p>}
        {deleteError && (
          <p
            role="alert"
            className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
          >
            {t(deleteError)}
          </p>
        )}
        {mine.data && mine.data.length === 0 && (
          <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted2">
            {t('You have not recorded a story yet.')}
          </p>
        )}
        <ul className="space-y-3">
          {(mine.data ?? []).map((s) => (
            <li key={s.id}>
              <Card className="flex gap-3 p-3">
                <Photo
                  photo={s.cover}
                  width={160}
                  className="h-20 w-20 shrink-0 rounded-lg object-cover"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/story/${s.id}`}
                      className="truncate font-serif text-[15px] text-ink hover:text-terracotta"
                    >
                      {s.title || 'Untitled story'}
                    </Link>
                    <Badge tone={STATUS_TONE[s.status]}>{t(STATUS_LABELS[s.status])}</Badge>
                  </div>
                  {s.place_name && (
                    <div className="mt-0.5 flex items-center gap-1 text-[11px] text-muted">
                      <MapPin size={11} /> {s.place_name}
                    </div>
                  )}
                  {s.held_for.length > 0 && (
                    <p className="mt-1 text-[12px] text-muted2">
                      {t('Held for a reviewer:')}
                      {s.held_for.map((l) => t(MODERATION_LABELS[l])).join(', ')}
                    </p>
                  )}
                  {s.review_note && (
                    <q className="mt-1 block text-[12px] italic text-muted2">{s.review_note}</q>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px]">
                    {(s.status === 'draft' || s.status === 'needs_edit') && (
                      <Link
                        to={`/create?story=${s.id}`}
                        className="font-semibold text-terracotta hover:underline"
                      >
                        {s.status === 'draft' ? t('Continue editing') : t('Edit and resubmit')}
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={() => void remove(s.id)}
                      disabled={deleting === s.id}
                      className={`hover:underline ${confirming === s.id ? 'font-semibold text-terracotta-dark' : 'text-muted'}`}
                    >
                      {deleting === s.id
                        ? t('Deleting…')
                        : confirming === s.id
                          ? t('Delete for good? Click again')
                          : t('Delete')}
                    </button>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <Bookmark size={16} className="text-terracotta" />
          <h3 className="font-serif text-lg">{t('Saved for later')}</h3>
          <span className="text-[11px] text-muted">{t('(examples)')}</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {saved.map((s) => (
            <Link
              key={s.id}
              to={`/story/${s.id}`}
              className="flex gap-3 rounded-xl border border-border bg-panel p-2.5 no-underline transition hover:bg-cream"
            >
              <Photo
                photo={s.cover}
                width={128}
                className="h-16 w-16 shrink-0 rounded-lg object-cover"
              />
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
