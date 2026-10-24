import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Clock,
  Compass,
  Filter,
  Layers,
  Navigation,
  Play,
  Search,
  Thermometer,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import JordanMap, { type JordanMapHandle } from '../components/JordanMap'
import Photo from '../components/Photo'
import { getFeed, getPins } from '../discover'
import { CATEGORY_LABELS, formatDuration } from '../stories'
import { toMapPins } from '../types'
import { useApi } from '../useApi'

const filters = ['All Stories', 'Museum', 'Ancient History', 'Oral Folklore', 'Crafts & Daily Life'] as const

function matchesFilter({ category, curated }: { category: string | null; curated: boolean }, filter: string) {
  if (filter === 'All Stories') return true
  // The museum is the stories staff have curated.
  if (filter === 'Museum') return curated
  if (filter === 'Ancient History') return category === 'history'
  if (filter === 'Oral Folklore') return category === 'folklore'
  if (filter === 'Crafts & Daily Life') return category === 'crafts' || category === 'daily_life'
  return true
}

export default function ExploreMapPage() {
  const mapRef = useRef<JordanMapHandle>(null)
  const [activeFilter, setActiveFilter] = useState<(typeof filters)[number]>('All Stories')
  const [query, setQuery] = useState('')
  const [mapMode, setMapMode] = useState<'compass' | 'time' | 'heat'>('compass')
  const feed = useApi(() => getFeed({ limit: 100 }), [])
  const pins = useApi(getPins, [])
  const stories = useMemo(() => feed.data?.items ?? [], [feed.data])
  const [focusedId, setFocusedId] = useState<string | null>(null)

  // Search across title, place, storyteller and excerpt; the server-side search arrives in #15.
  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    return stories.filter((s) => {
      if (!matchesFilter(s, activeFilter)) return false
      if (!q) return true
      return (
        s.title.toLowerCase().includes(q) ||
        s.place_name.toLowerCase().includes(q) ||
        s.author.display_name.toLowerCase().includes(q) ||
        s.excerpt.toLowerCase().includes(q)
      )
    })
  }, [stories, activeFilter, query])

  useEffect(() => {
    if (!focusedId && stories.length) setFocusedId((stories.find((s) => s.curated) ?? stories[0]).id)
  }, [stories, focusedId])

  const focused = stories.find((s) => s.id === focusedId) ?? results[0] ?? null

  const visiblePins = useMemo(
    () => toMapPins((pins.data ?? []).filter((p) => results.some((s) => s.id === p.story_id))),
    [pins.data, results],
  )

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col px-4 pb-0 pt-6 sm:px-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl">Explore Jordan</h1>
          <p className="text-sm text-muted">
            {feed.loading ? 'Loading stories…' : `Discover ${stories.length} stories across the Kingdom`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setActiveFilter(f)}
              className={`rounded-full border px-3.5 py-2 text-xs transition ${
                activeFilter === f
                  ? 'border-terracotta bg-terracotta text-cream'
                  : 'border-border text-muted2 hover:bg-cream'
              }`}
            >
              {f}
            </button>
          ))}
          <button className="flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted2">
            <Layers size={14} />
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 pb-6 lg:grid-cols-[340px_1fr]">
        <Card className="flex min-h-0 flex-col p-4">
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-cream px-3 py-2">
            <Search size={14} className="text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter results by location or narrator…"
              className="w-full bg-transparent text-xs outline-none placeholder:text-muted"
            />
          </div>
          <div className="mb-2 flex items-center justify-between text-[11px] text-muted">
            <span>RESULTS FOUND: {results.length}</span>
            <span>Newest first</span>
          </div>

          <div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto pr-1">
            {results.map((r) => (
              <button
                key={r.id}
                onClick={() => setFocusedId(r.id)}
                className={`flex w-full gap-3 rounded-lg border p-2.5 text-left transition ${
                  focusedId === r.id
                    ? 'border-terracotta bg-terracotta-light/40'
                    : 'border-transparent hover:bg-cream'
                }`}
              >
                <Photo photo={r.cover} width={112} className="h-14 w-14 shrink-0 rounded-md object-cover" />
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded-full bg-terracotta-light px-2 py-0.5 text-[9px] font-semibold uppercase text-terracotta-dark">
                      {r.category ? CATEGORY_LABELS[r.category] : 'Story'}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-muted">
                      <Clock size={10} /> {formatDuration(r.duration_ms)}
                    </span>
                    {r.curated && <Badge tone="teal">Curated</Badge>}
                  </div>
                  <div className="truncate text-[13px] font-medium">{r.title}</div>
                  <div className="truncate text-[11px] text-muted">{r.excerpt}</div>
                  <div className="mt-1 text-[10px] text-muted2">Told by {r.author.display_name}</div>
                </div>
              </button>
            ))}
            {feed.error && <p className="py-8 text-center text-xs text-terracotta-dark">{feed.error}</p>}
            {!feed.loading && !feed.error && results.length === 0 && (
              <p className="py-8 text-center text-xs text-muted">No stories match this filter.</p>
            )}
          </div>

          {focused && (
            <div className="mt-3 border-t border-border pt-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-terracotta">
                <Navigation size={12} /> Currently focused
              </div>
              <div className="mb-3 font-serif text-sm">{focused.title}</div>
              <div className="flex gap-2">
                <Link to={`/story/${focused.id}`} className="flex-1">
                  <PillButton variant="primary" className="w-full justify-center !py-2">
                    <Play size={13} /> Listen now
                  </PillButton>
                </Link>
                <Link to={`/story/${focused.id}`} className="flex-1">
                  <PillButton variant="outline" className="w-full justify-center !py-2">
                    View details
                  </PillButton>
                </Link>
              </div>
            </div>
          )}
        </Card>

        <Card className="relative min-h-[420px] overflow-hidden">
          <JordanMap
            ref={mapRef}
            pins={visiblePins}
            focusedStoryId={focusedId}
            onSelectStory={(id) => setFocusedId(id)}
            className="absolute inset-0"
          />

          <div className="pointer-events-none absolute right-4 top-4 z-10 w-52 rounded-xl bg-panel/95 px-4 py-3 text-[11px] shadow-sm">
            <div className="pointer-events-auto">
              <div className="mb-2 flex items-center justify-between font-semibold">
                Map legend <span className="h-1.5 w-1.5 rounded-full bg-teal" />
              </div>
              <div className="space-y-1.5 text-muted2">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-terracotta" /> In the museum
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-gold" /> Other stories
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-teal" /> Recently added
                </div>
              </div>
              <p className="mt-2 border-t border-border pt-2 text-[10px] text-muted">
                Click pins to preview. Drag to pan Jordan.
              </p>
            </div>
          </div>

          {focused && (
            <div className="absolute bottom-16 left-4 z-10 w-64 rounded-xl bg-panel p-3 shadow-md">
              <div className="flex gap-2">
                <Photo photo={focused.cover} width={96} className="h-12 w-12 rounded-md object-cover" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[10px] uppercase text-muted">{focused.title}</div>
                  <div className="text-[11px] text-muted2">Told by {focused.author.display_name}</div>
                </div>
                <Link
                  to={`/story/${focused.id}`}
                  aria-label={`Listen to ${focused.title}`}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-terracotta text-cream"
                >
                  <Play size={12} fill="currentColor" />
                </Link>
              </div>
            </div>
          )}

          <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-2">
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-panel"
              onClick={() => mapRef.current?.zoomIn()}
              aria-label="Zoom in"
            >
              <ZoomIn size={14} />
            </button>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-panel"
              onClick={() => mapRef.current?.zoomOut()}
              aria-label="Zoom out"
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-terracotta text-cream"
              onClick={() => mapRef.current?.reset()}
              aria-label="Reset map"
            >
              <Navigation size={14} />
            </button>
          </div>

          <div className="absolute bottom-4 left-4 z-10 flex max-w-[calc(100%-5rem)] items-center gap-3 overflow-x-auto rounded-full bg-ink/90 px-4 py-2 text-[11px] text-cream lg:left-1/2 lg:-translate-x-1/2">
            <span className="flex shrink-0 items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-teal" /> Map active
            </span>
            <button
              onClick={() => setMapMode('compass')}
              className={`flex shrink-0 items-center gap-1 ${mapMode === 'compass' ? 'text-terracotta-light' : ''}`}
            >
              <Compass size={12} /> Compass view
            </button>
            <button
              onClick={() => setMapMode('time')}
              className={`hidden shrink-0 items-center gap-1 sm:flex ${mapMode === 'time' ? 'text-terracotta-light' : ''}`}
            >
              <Clock size={12} /> Time layers
            </button>
            <button
              onClick={() => setMapMode('heat')}
              className={`hidden shrink-0 items-center gap-1 sm:flex ${mapMode === 'heat' ? 'text-terracotta-light' : ''}`}
            >
              <Thermometer size={12} /> Heatmap
            </button>
            <button className="flex shrink-0 items-center gap-1">
              <Filter size={12} />
            </button>
          </div>
        </Card>
      </div>
    </div>
  )
}
