import { captions } from '../captions'
import { message, t, useLocale } from '../i18n'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bookmark,
  ChevronRight,
  Heart,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Share2,
  Volume2,
} from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import TranscriptView from '../components/TranscriptView'
import StoryStatusBanner from '../components/StoryStatusBanner'
import MediaProgress from '../components/MediaProgress'
import StaffNarrator from '../components/StaffNarrator'
import { ApiError } from '../api'
import { initials } from '../auth'
import Photo from '../components/Photo'
import { getFeed, getPlaces, type Photo as PhotoData } from '../discover'
import Avatar from '../components/Avatar'
import { engagementFor, sampleReflections } from '../demo/mockEngagement'
import {
  CATEGORY_LABELS,
  LANGUAGE_LABELS,
  LAYER_LABELS,
  formatDuration,
  getStory,
  isStoryId,
  type StoryRecord,
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
  narration: StoryRecord['narration']
  slideshow: StoryRecord['slideshow']
  languageLabel: string | null
  layers: TextLayer[]
  photos: PhotoData[]
  record: StoryRecord
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
    narration: s.narration,
    slideshow: s.slideshow,
    languageLabel: s.original_language ? LANGUAGE_LABELS[s.original_language] : null,
    layers: s.layers,
    photos: s.photos.map((p) => p.photo),
    record: s,
  }
}

function fmt(s: number) {
  if (!Number.isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  const sec = String(Math.floor(s % 60)).padStart(2, '0')
  return `${m}:${sec}`
}

type Load =
  | { state: 'loading' }
  | { state: 'missing' }
  | { state: 'error'; message: string }
  | { state: 'ready'; story: PlayerStory }

export default function StoryPlayerPage() {
  useLocale()

  const { id } = useParams()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const onStoryChange = useCallback(
    (record: StoryRecord) => setLoad({ state: 'ready', story: fromRecord(record) }),
    [],
  )

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
        else
          setLoad({
            state: 'error',
            message: e instanceof Error ? e.message : t('Could not load the story.'),
          })
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (load.state === 'loading') {
    return <div className="p-12 text-center text-sm text-muted">{t('Loading story…')}</div>
  }
  if (load.state === 'missing' || load.state === 'error') {
    return (
      <div className="mx-auto max-w-md p-12 text-center">
        <h1 className="mb-2 font-serif text-2xl">
          {load.state === 'missing' ? t('Story not found') : t('Something went wrong')}
        </h1>
        <p className="mb-6 text-sm text-muted2">
          {load.state === 'missing'
            ? t('This story does not exist, or it is not published yet.')
            : load.message}
        </p>
        <Link to="/explore" className="text-sm font-medium text-terracotta hover:underline">
          {t('Explore other stories')}
        </Link>
      </div>
    )
  }
  // Keyed by story, so following a link to another story starts its player afresh.
  return <Player key={load.story.id} story={load.story} onStoryChange={onStoryChange} />
}

function Player({
  story,
  onStoryChange,
}: {
  story: PlayerStory
  onStoryChange: (record: StoryRecord) => void
}) {
  useLocale()

  const audioRef = useRef<HTMLAudioElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  // Listen to the storyteller's own recording, or to the narration of the text.
  const [mode, setMode] = useState<'original' | 'narrated'>(
    story.audioUrl ? 'original' : 'narrated',
  )
  // After switching, continue at the same line in the other track.
  const resumeAt = useRef<{ seconds: number; play: boolean } | null>(null)
  // The slideshow carries the narration, so while it plays the lines follow its timings.
  const [videoPlaying, setVideoPlaying] = useState(false)
  // Bumped when staff ask for a new narration, so the progress card looks again.
  const [mediaRound, setMediaRound] = useState(0)
  const [videoTime, setVideoTime] = useState(0)
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

  const lineTimes = (m: 'original' | 'narrated') =>
    m === 'narrated' ? (story.narration?.segments ?? []) : (story.layers[0]?.segments ?? [])

  function switchTo(next: 'original' | 'narrated') {
    if (next === mode) return
    const el = audioRef.current
    const ms = elapsed * 1000
    const line = lineTimes(mode).findIndex((s) => ms >= s.start_ms && ms < s.end_ms)
    const target = line >= 0 ? (lineTimes(next)[line]?.start_ms ?? 0) / 1000 : 0
    resumeAt.current = { seconds: target, play: !!el && !el.paused }
    el?.pause()
    setAudioError(false)
    setElapsed(target)
    // Until the new track's own length loads, use the length its timings give.
    const lines = lineTimes(next)
    setDuration(lines.length ? lines[lines.length - 1].end_ms / 1000 : story.durationSec)
    setMode(next)
  }

  function seekTo(seconds: number) {
    const el = audioRef.current
    if (!el || !duration) return
    el.currentTime = Math.min(Math.max(0, seconds), duration)
    setElapsed(el.currentTime)
  }

  const src = mode === 'narrated' ? (story.narration?.url ?? null) : story.audioUrl
  const canPlay = !!src && !audioError
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
      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={() => {
            setPlaying(true)
            videoRef.current?.pause()
          }}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setElapsed(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => {
            const el = e.currentTarget
            if (Number.isFinite(el.duration)) setDuration(el.duration)
            const resume = resumeAt.current
            resumeAt.current = null
            if (resume) {
              el.currentTime = resume.seconds
              if (resume.play) el.play().catch(() => setAudioError(true))
            }
          }}
          onError={() => setAudioError(true)}
        >
          <track
            kind="captions"
            srcLang={story.record.original_language === 'english' ? 'en' : 'ar'}
            label={t('Transcript')}
            src={captions(
              mode === 'narrated'
                ? story.narration?.segments
                : story.layers.find((layer) => layer.kind === 'verbatim')?.segments,
            )}
          />
        </audio>
      )}

      <div className="flex items-center justify-between mb-4 text-sm">
        <div className="text-muted flex items-center gap-1.5">
          <Link to="/">{t('Home')}</Link> <ChevronRight className="rtl:rotate-180" size={13} />{' '}
          <Link to="/explore">{t('Explore')}</Link>{' '}
          <ChevronRight className="rtl:rotate-180" size={13} />{' '}
          <span className="text-ink">{t('Story Player')}</span>
        </div>
        <div className="flex items-center gap-2">
          <PillButton variant="outline" className="!py-1.5 !px-3 text-xs">
            <Share2 size={13} /> {t('Share')}
          </PillButton>
          <button
            onClick={() => setSaved((s) => !s)}
            aria-pressed={saved}
            className={`text-xs px-3 py-1.5 rounded-full border flex items-center gap-1.5 ${saved ? 'bg-terracotta-light text-terracotta-dark border-terracotta-light' : 'border-border text-muted2'}`}
          >
            <Bookmark size={13} fill={saved ? 'currentColor' : 'none'} />{' '}
            {saved ? t('Saved') : t('Save')}
          </button>
        </div>
      </div>

      <StoryStatusBanner story={story.record} onChange={onStoryChange} />
      <MediaProgress key={mediaRound} story={story.record} onChange={onStoryChange} />

      <div className="grid lg:grid-cols-[minmax(0,1fr)_340px] gap-6">
        <div>
          <div className="relative h-72 rounded-xl2 overflow-hidden mb-4">
            <Photo
              photo={story.cover}
              width={1000}
              sizes="(min-width: 1024px) 760px, 100vw"
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
            <div className="absolute top-4 start-4 flex gap-2">
              {story.category && <Badge tone="terracotta">{story.category}</Badge>}
              {story.curated && <Badge tone="teal">{t('Curated')}</Badge>}
            </div>
            <div className="absolute bottom-4 start-4 text-cream">
              <h1 className="font-serif text-2xl">{story.title}</h1>
              <div className="text-xs text-cream/80 mt-1">
                {[story.durationLabel, story.place && `${story.place}, Jordan`]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
          </div>

          {/* player bar */}
          <Card className="p-4 mb-6">
            {story.narration && story.audioUrl && (
              <div className="mb-3 flex justify-center">
                <div
                  role="radiogroup"
                  aria-label={t('What to listen to')}
                  className="inline-flex rounded-full bg-cream p-1 text-xs"
                >
                  {(['original', 'narrated'] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      role="radio"
                      aria-checked={mode === m}
                      onClick={() => switchTo(m)}
                      className={`rounded-full px-3 py-1 font-medium ${mode === m ? 'bg-terracotta text-cream' : 'text-muted2'}`}
                    >
                      {m === 'original' ? t('Storyteller') : t('Narration')}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[11px] text-muted w-10">{fmt(elapsed)}</span>
              <div
                role="slider"
                tabIndex={canPlay ? 0 : -1}
                aria-label={t('Playback position')}
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
                <div
                  className="h-full bg-gradient-to-r from-terracotta to-gold"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-[11px] text-muted w-10 text-end">{fmt(duration)}</span>
            </div>
            <div className="flex items-center justify-center gap-6 text-muted2">
              <button
                type="button"
                aria-label={t('Back 15 seconds')}
                disabled={!canPlay}
                onClick={() => seekTo(elapsed - 15)}
                className="disabled:opacity-40"
              >
                <RotateCcw size={18} />
              </button>
              <button
                type="button"
                onClick={togglePlay}
                disabled={!canPlay}
                aria-label={playing ? t('Pause') : t('Play')}
                className="w-11 h-11 rounded-full bg-terracotta text-cream flex items-center justify-center disabled:opacity-50"
              >
                {playing ? <Pause size={18} /> : <Play size={18} />}
              </button>
              <button
                type="button"
                aria-label={t('Forward 15 seconds')}
                disabled={!canPlay}
                onClick={() => seekTo(elapsed + 15)}
                className="disabled:opacity-40"
              >
                <RotateCw size={18} />
              </button>
              <label className="flex items-center gap-1.5 ms-4">
                <Volume2 size={15} aria-hidden />
                <span className="sr-only">{t('Volume')}</span>
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
            {mode === 'narrated' && story.narration && (
              <p className="mt-3 text-center text-[11px] text-muted">
                {t('A voice reads the')}
                {t(
                  LAYER_LABELS[story.narration.source === 'msa' ? 'translation_msa' : 'polished'],
                )}{' '}
                {t('text.')}
                {story.narration.narrated_by && (
                  <>
                    {' '}
                    {message('Narrated in the voice of {name}.', {
                      name: story.narration.narrated_by,
                    })}
                  </>
                )}
              </p>
            )}
            {!canPlay && (
              <p className="mt-3 text-center text-[11px] text-muted">
                {audioError
                  ? t('The recording could not be played.')
                  : t('This demo story has text only; its recording has not been added.')}
              </p>
            )}
          </Card>

          <StaffNarrator story={story.record} onQueued={() => setMediaRound((r) => r + 1)} />

          {story.record.ai_video && (
            <div className="mb-6">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {t('AI video preview')}
              </div>
              {story.record.ai_video.locked || !story.record.ai_video.video_url ? (
                <div className="relative overflow-hidden rounded-xl2">
                  <img
                    src={story.record.ai_video.poster_url}
                    alt=""
                    className="aspect-video w-full object-cover opacity-60"
                  />
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/40 p-4 text-center text-cream">
                    <p className="text-sm">{t('Premium unlocks this AI video preview.')}</p>
                    <Link
                      to="/premium"
                      className="rounded-full bg-terracotta px-4 py-2 text-xs font-semibold text-cream"
                    >
                      {t('Unlock with Premium')}
                    </Link>
                  </div>
                </div>
              ) : (
                <video
                  src={story.record.ai_video.video_url}
                  poster={story.record.ai_video.poster_url}
                  controls
                  preload="none"
                  className="aspect-video w-full rounded-xl2 bg-black"
                  aria-label={`${t('AI video preview')}: ${story.record.ai_video.title}`}
                >
                  {/* The sample is silent; the caption says what it shows. */}
                  <track
                    kind="captions"
                    srcLang="en"
                    label={t('Description')}
                    src={captions([
                      { start_ms: 0, end_ms: 6000, text: story.record.ai_video.title },
                    ])}
                    default
                  />
                </video>
              )}
              <p className="mt-2 text-[11px] text-muted">
                {t(story.record.ai_video.note)} {t('Credit:')}{' '}
                <a
                  href={story.record.ai_video.source_url}
                  className="underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  {story.record.ai_video.credit}
                </a>
              </p>
            </div>
          )}

          {story.slideshow && (
            <div className="mb-6">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {t('Slideshow')}
              </div>
              <video
                ref={videoRef}
                src={story.slideshow.url}
                controls
                preload="metadata"
                poster={story.cover?.urls['1600'] ?? story.cover?.urls['960']}
                onPlay={() => {
                  audioRef.current?.pause()
                  setVideoPlaying(true)
                }}
                onPause={() => setVideoPlaying(false)}
                onEnded={() => setVideoPlaying(false)}
                onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
                className="aspect-video w-full rounded-xl2 bg-black"
                aria-label={`${t('Slideshow')}: ${story.title}`}
              >
                <track
                  kind="captions"
                  srcLang={story.narration?.language === 'english' ? 'en' : 'ar'}
                  label={t('Transcript')}
                  src={captions(story.narration?.segments)}
                  default
                />
              </video>
            </div>
          )}

          {gallery.length > 0 && (
            <div className="mb-6">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {story.photos.length ? t('Photos') : `${story.place} gallery`}
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
              <div className="font-serif text-base mb-2">{t('About this story')}</div>
              <dl className="space-y-1.5 text-sm text-muted2">
                {story.category && (
                  <div>
                    <dt className="inline font-medium text-ink2">{t('Category:')} </dt>
                    <dd className="inline">{story.category}</dd>
                  </div>
                )}
                {story.place && (
                  <div>
                    <dt className="inline font-medium text-ink2">{t('Place:')} </dt>
                    <dd className="inline">
                      {story.place}
                      {t(', Jordan')}
                    </dd>
                  </div>
                )}
                {story.languageLabel && (
                  <div>
                    <dt className="inline font-medium text-ink2">{t('Told in:')} </dt>
                    <dd className="inline">{story.languageLabel}</dd>
                  </div>
                )}
                {story.durationLabel && (
                  <div>
                    <dt className="inline font-medium text-ink2">{t('Length:')} </dt>
                    <dd className="inline">{story.durationLabel}</dd>
                  </div>
                )}
              </dl>
            </Card>
            <Card className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-terracotta-light text-sm font-semibold text-terracotta-dark">
                  {initials(story.narrator)}
                </span>
                <div>
                  <div className="text-sm font-semibold">{story.narrator}</div>
                  <div className="text-[11px] text-terracotta">{t('Storyteller')}</div>
                </div>
              </div>
            </Card>
          </div>

          {/* community reflections: mock (see demo/mockEngagement) */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-serif text-xl">{t('Community Reflections')}</h2>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            {sampleReflections.map((c) => (
              <Card key={c.name} className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Avatar name={c.name} className="h-8 w-8" />
                  <div>
                    <div className="text-[12px] font-semibold">{c.name}</div>
                    <div className="text-[10px] text-muted">{c.timeAgo}</div>
                  </div>
                </div>
                <p className="text-[12.5px] italic text-ink2 mb-3">"{c.text}"</p>
                <div className="flex items-center gap-4 text-[11px] text-muted">
                  <span className="flex items-center gap-1">
                    <Heart size={11} /> {c.likes}
                  </span>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* right column */}
        <div>
          <Card className="p-1 mb-4">
            <div className="flex" role="tablist">
              {(['transcript', 'accessibility'] as const).map((tabName) => (
                <button
                  key={t(tabName === 'transcript' ? 'Transcript' : 'Accessibility')}
                  role="tab"
                  aria-selected={tab === tabName}
                  onClick={() => setTab(tabName)}
                  className={`flex-1 text-xs font-medium py-2.5 rounded-lg capitalize ${tab === tabName ? 'bg-cream text-ink' : 'text-muted'}`}
                >
                  {t(tabName === 'transcript' ? 'Transcript' : 'Accessibility')}
                </button>
              ))}
            </div>
          </Card>

          {tab === 'transcript' ? (
            story.layers.length > 0 ? (
              <TranscriptView
                layers={story.layers}
                elapsedMs={(videoPlaying ? videoTime : elapsed) * 1000}
                following={playing || videoPlaying}
                timing={mode === 'narrated' || videoPlaying ? story.narration?.segments : null}
                onSeek={(ms) => {
                  if (videoPlaying && videoRef.current) {
                    videoRef.current.currentTime = ms / 1000
                    return
                  }
                  seekTo(ms / 1000)
                  if (canPlay && !playing) togglePlay()
                }}
              />
            ) : (
              <Card className="p-4 mb-4 text-[13px] text-muted2 leading-relaxed">
                {t(
                  'The transcript and translations appear here once the story has been processed.',
                )}
              </Card>
            )
          ) : (
            <Card className="p-4 mb-4 text-[13px] text-muted2 leading-relaxed">
              {t(
                'The player works with a keyboard and screen readers. The transcript, once ready, follows the recording line by line.',
              )}
            </Card>
          )}

          <div className="grid grid-cols-2 gap-3 mb-6">
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">{mock.likes.toLocaleString()}</div>
              <div className="text-[11px] text-muted">{t('Likes')}</div>
            </Card>
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">{mock.comments}</div>
              <div className="text-[11px] text-muted">{t('Comments')}</div>
            </Card>
          </div>

          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">
              {t('Up next')}
            </div>
          </div>
          <div className="space-y-2">
            {upNext.map((u) => (
              <Link
                to={`/story/${u.id}`}
                key={u.id}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-cream"
              >
                <Photo
                  photo={u.cover}
                  width={88}
                  className="w-11 h-11 shrink-0 rounded-md object-cover"
                />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate">{u.title}</div>
                  <div className="text-[11px] text-muted">
                    {u.author.display_name} · {formatDuration(u.duration_ms)}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <footer className="mt-12 pt-5 border-t border-border flex flex-wrap justify-between gap-2 text-[11px] text-muted">
        <div className="flex gap-4">
          <span>{t('Privacy Policy')}</span>
          <span>{t('Usage Guidelines')}</span>
          <span>{t('Contact Archive')}</span>
        </div>
        <div>
          © {new Date().getFullYear()} {t('Hikaya (حكاية) — Preserving Our Digital Silk Road.')}
        </div>
      </footer>
    </div>
  )
}
