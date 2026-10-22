import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bookmark, ChevronRight, Heart, Pause, Play, RotateCcw, RotateCw, Share2, Volume2,
} from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import TranscriptView from '../components/TranscriptView'
import { ApiError } from '../api'
import { initials } from '../auth'
import Photo from '../components/Photo'
import { getFeed, getPlaces, type Photo as PhotoData } from '../discover'
import { engagementFor, mockAvatarUrl, sampleReflections } from '../demo/mockEngagement'
import {
  CATEGORY_LABELS, LANGUAGE_LABELS, formatDuration, getStory, isStoryId, type StoryRecord,
  type TextLayer,
} from '../stories'
import { useApi } from '../useApi'

/** What the page needs from a story. */
interface PlayerStory {
  id: string
  title: string
  place: string
  placeSlug: string | null
  category: string
  narrator: string
  durationLabel: string
  durationSec: number
  cover: PhotoData | null
  curated: boolean
  audioUrl: string | null
  languageLabel: string | null
  layers: TextLayer[]
  photos: PhotoData[]
}

function fromRecord(s: StoryRecord): PlayerStory {
  return {
    id: s.id,
    title: s.title,
    place: s.place_name,
    placeSlug: s.place_slug,
    category: s.category ? CATEGORY_LABELS[s.category] : '',
    narrator: s.author.display_name,
    durationLabel: formatDuration(s.duration_ms),
    durationSec: (s.duration_ms ?? 0) / 1000,
    cover: s.cover,
    curated: s.curated,
    audioUrl: s.audio?.url ?? null,
    languageLabel: s.original_language ? LANGUAGE_LABELS[s.original_language] : null,
    layers: s.layers,
    photos: s.photos.map((p) => p.photo),
  }
}

function fmt(s: number) {
  if (!Number.isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  const sec = String(Math.floor(s % 60)).padStart(2, '0')
  return `${m}:${sec}`
}

type Load = { state: 'loading' } | { state: 'missing' } | { state: 'error'; message: string } | { state: 'ready'; story: PlayerStory }

export default function StoryPlayerPage() {
  const { id } = useParams()
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    if (!isStoryId(id)) {
      setLoad({ state: 'missing' })
      return
    }
    let cancelled = false
    setLoad({ state: 'loading' })
    getStory(id)
      .then((s) => !cancelled && setLoad({ state: 'ready', story: fromRecord(s) }))
      .catch((e) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 404) setLoad({ state: 'missing' })
        else setLoad({ state: 'error', message: e instanceof Error ? e.message : 'Could not load the story.' })
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (load.state === 'loading') {
    return <div className="p-12 text-center text-sm text-muted">Loading story…</div>
  }
  if (load.state === 'missing' || load.state === 'error') {
    return (
      <div className="mx-auto max-w-md p-12 text-center">
        <h1 className="mb-2 font-serif text-2xl">
          {load.state === 'missing' ? 'Story not found' : 'Something went wrong'}
        </h1>
        <p className="mb-6 text-sm text-muted2">
          {load.state === 'missing'
            ? 'This story does not exist, or it is not published yet.'
            : load.message}
        </p>
        <Link to="/explore" className="text-sm font-medium text-terracotta hover:underline">
          Explore other stories
        </Link>
      </div>
    )
  }
  return <Player story={load.story} />
}

function Player({ story }: { story: PlayerStory }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [tab, setTab] = useState<'transcript' | 'accessibility'>('transcript')
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [duration, setDuration] = useState(story.durationSec)
  const [volume, setVolume] = useState(0.8)
  const [audioError, setAudioError] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume
  }, [volume])

  function togglePlay() {
    const el = audioRef.current
    if (!el) return
    if (el.paused) {
      el.play().catch(() => setAudioError(true))
    } else {
      el.pause()
    }
  }

  function seekTo(seconds: number) {
    const el = audioRef.current
    if (!el || !duration) return
    el.currentTime = Math.min(Math.max(0, seconds), duration)
    setElapsed(el.currentTime)
  }

  const canPlay = !!story.audioUrl && !audioError
  const progress = duration ? Math.min(100, (elapsed / duration) * 100) : 0
  const places = useApi(getPlaces, [])
  // The story's own photos first; otherwise the gallery of its place.
  const gallery = story.photos.length
    ? story.photos
    : (places.data?.find((p) => p.slug === story.placeSlug)?.photos ?? [])
  const feed = useApi(() => getFeed({ limit: 4 }), [])
  const upNext = (feed.data?.items ?? []).filter((s) => s.id !== story.id).slice(0, 3)
  const mock = engagementFor(story.id)

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto">
      {story.audioUrl && (
        <audio
          ref={audioRef}
          src={story.audioUrl}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setElapsed(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => {
            if (Number.isFinite(e.currentTarget.duration)) setDuration(e.currentTarget.duration)
          }}
          onError={() => setAudioError(true)}
        />
      )}

      <div className="flex items-center justify-between mb-4 text-sm">
        <div className="text-muted flex items-center gap-1.5">
          <Link to="/">Home</Link> <ChevronRight size={13} /> <Link to="/explore">Explore</Link> <ChevronRight size={13} /> <span className="text-ink">Story Player</span>
        </div>
        <div className="flex items-center gap-2">
          <PillButton variant="outline" className="!py-1.5 !px-3 text-xs"><Share2 size={13} /> Share</PillButton>
          <button
            onClick={() => setSaved((s) => !s)}
            aria-pressed={saved}
            className={`text-xs px-3 py-1.5 rounded-full border flex items-center gap-1.5 ${saved ? 'bg-terracotta-light text-terracotta-dark border-terracotta-light' : 'border-border text-muted2'}`}
          >
            <Bookmark size={13} fill={saved ? 'currentColor' : 'none'} /> {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_340px] gap-6">
        <div>
          <div className="relative h-72 rounded-xl2 overflow-hidden mb-4">
            <Photo photo={story.cover} width={1000} sizes="(min-width: 1024px) 760px, 100vw" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
            <div className="absolute top-4 left-4 flex gap-2">
              {story.category && <Badge tone="terracotta">{story.category}</Badge>}
              {story.curated && <Badge tone="teal">Curated</Badge>}
            </div>
            <div className="absolute bottom-4 left-4 text-cream">
              <h1 className="font-serif text-2xl">{story.title}</h1>
              <div className="text-xs text-cream/80 mt-1">
                {[story.durationLabel, story.place && `${story.place}, Jordan`].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>

          {/* player bar */}
          <Card className="p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[11px] text-muted w-10">{fmt(elapsed)}</span>
              <div
                role="slider"
                tabIndex={canPlay ? 0 : -1}
                aria-label="Playback position"
                aria-valuemin={0}
                aria-valuemax={Math.round(duration)}
                aria-valuenow={Math.round(elapsed)}
                aria-valuetext={`${fmt(elapsed)} of ${fmt(duration)}`}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  seekTo(((e.clientX - rect.left) / rect.width) * duration)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowRight') seekTo(elapsed + 5)
                  if (e.key === 'ArrowLeft') seekTo(elapsed - 5)
                }}
                className={`flex-1 h-1.5 bg-border rounded-full overflow-hidden ${canPlay ? 'cursor-pointer' : ''}`}
              >
                <div className="h-full bg-gradient-to-r from-terracotta to-gold" style={{ width: `${progress}%` }} />
              </div>
              <span className="text-[11px] text-muted w-10 text-right">{fmt(duration)}</span>
            </div>
            <div className="flex items-center justify-center gap-6 text-muted2">
              <button type="button" aria-label="Back 15 seconds" disabled={!canPlay} onClick={() => seekTo(elapsed - 15)} className="disabled:opacity-40">
                <RotateCcw size={18} />
              </button>
              <button
                type="button"
                onClick={togglePlay}
                disabled={!canPlay}
                aria-label={playing ? 'Pause' : 'Play'}
                className="w-11 h-11 rounded-full bg-terracotta text-cream flex items-center justify-center disabled:opacity-50"
              >
                {playing ? <Pause size={18} /> : <Play size={18} />}
              </button>
              <button type="button" aria-label="Forward 15 seconds" disabled={!canPlay} onClick={() => seekTo(elapsed + 15)} className="disabled:opacity-40">
                <RotateCw size={18} />
              </button>
              <label className="flex items-center gap-1.5 ml-4">
                <Volume2 size={15} aria-hidden />
                <span className="sr-only">Volume</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={volume}
                  onChange={(e) => setVolume(Number(e.target.value))}
                  className="w-16 accent-terracotta"
                />
              </label>
            </div>
            {!canPlay && (
              <p className="mt-3 text-center text-[11px] text-muted">
                {audioError
                  ? 'The recording could not be played.'
                  : 'This demo story has text only; its recording has not been added.'}
              </p>
            )}
          </Card>

          {gallery.length > 0 && (
            <div className="mb-6">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {story.photos.length ? 'Photos' : `${story.place} gallery`}
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {gallery.map((photo) => (
                  <Photo
                    key={photo.slug}
                    photo={photo}
                    width={288}
                    alt={photo.caption}
                    className="h-24 w-36 shrink-0 rounded-lg border border-border object-cover"
                  />
                ))}
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-5 mb-8">
            <Card className="p-5">
              <div className="font-serif text-base mb-2">About this story</div>
              <dl className="space-y-1.5 text-sm text-muted2">
                {story.category && <div><dt className="inline font-medium text-ink2">Category: </dt><dd className="inline">{story.category}</dd></div>}
                {story.place && <div><dt className="inline font-medium text-ink2">Place: </dt><dd className="inline">{story.place}, Jordan</dd></div>}
                {story.languageLabel && <div><dt className="inline font-medium text-ink2">Told in: </dt><dd className="inline">{story.languageLabel}</dd></div>}
                {story.durationLabel && <div><dt className="inline font-medium text-ink2">Length: </dt><dd className="inline">{story.durationLabel}</dd></div>}
              </dl>
            </Card>
            <Card className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-terracotta-light text-sm font-semibold text-terracotta-dark">
                  {initials(story.narrator)}
                </span>
                <div>
                  <div className="text-sm font-semibold">{story.narrator}</div>
                  <div className="text-[11px] text-terracotta">Storyteller</div>
                </div>
              </div>
            </Card>
          </div>

          {/* community reflections: mock (see demo/mockEngagement) */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-serif text-xl">Community Reflections</h2>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            {sampleReflections.map((c) => (
              <Card key={c.name} className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <img src={mockAvatarUrl(c.avatarSeed, 60)} className="w-8 h-8 rounded-full object-cover" alt="" />
                  <div>
                    <div className="text-[12px] font-semibold">{c.name}</div>
                    <div className="text-[10px] text-muted">{c.timeAgo}</div>
                  </div>
                </div>
                <p className="text-[12.5px] italic text-ink2 mb-3">"{c.text}"</p>
                <div className="flex items-center gap-4 text-[11px] text-muted">
                  <span className="flex items-center gap-1"><Heart size={11} /> {c.likes}</span>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* right column */}
        <div>
          <Card className="p-1 mb-4">
            <div className="flex" role="tablist">
              {(['transcript', 'accessibility'] as const).map((t) => (
                <button
                  key={t}
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                  className={`flex-1 text-xs font-medium py-2.5 rounded-lg capitalize ${tab === t ? 'bg-cream text-ink' : 'text-muted'}`}
                >
                  {t}
                </button>
              ))}
            </div>
          </Card>

          {tab === 'transcript' ? (
            story.layers.length > 0 ? (
              <TranscriptView
                layers={story.layers}
                elapsedMs={elapsed * 1000}
                following={playing}
                onSeek={(ms) => {
                  seekTo(ms / 1000)
                  if (canPlay && !playing) togglePlay()
                }}
              />
            ) : (
              <Card className="p-4 mb-4 text-[13px] text-muted2 leading-relaxed">
                The transcript and translations appear here once the story has been processed.
              </Card>
            )
          ) : (
            <Card className="p-4 mb-4 text-[13px] text-muted2 leading-relaxed">
              The player works with a keyboard and screen readers. The transcript, once ready, follows the recording line by line.
            </Card>
          )}

          <div className="grid grid-cols-2 gap-3 mb-6">
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">{mock.likes.toLocaleString()}</div>
              <div className="text-[11px] text-muted">Likes</div>
            </Card>
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">{mock.comments}</div>
              <div className="text-[11px] text-muted">Comments</div>
            </Card>
          </div>

          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Up next</div>
          </div>
          <div className="space-y-2">
            {upNext.map((u) => (
              <Link to={`/story/${u.id}`} key={u.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-cream">
                <Photo photo={u.cover} width={88} className="w-11 h-11 shrink-0 rounded-md object-cover" />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate">{u.title}</div>
                  <div className="text-[11px] text-muted">{u.author.display_name} · {formatDuration(u.duration_ms)}</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <footer className="mt-12 pt-5 border-t border-border flex flex-wrap justify-between gap-2 text-[11px] text-muted">
        <div className="flex gap-4">
          <span>Privacy Policy</span><span>Usage Guidelines</span><span>Contact Archive</span>
        </div>
        <div>© {new Date().getFullYear()} Hikaya (حكاية) — Preserving Our Digital Silk Road.</div>
      </footer>
    </div>
  )
}
