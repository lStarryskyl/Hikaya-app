import { useMemo, useRef, useState } from 'react'
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
import { Card, PillButton } from '../components/ui'
import JordanMap, { type JordanMapHandle } from '../components/JordanMap'
import { mapPins, stories, imageUrl } from '../data/mock'

const filters = ['All Stories', 'Ancient History', 'Oral Folklore', 'Heritage Music'] as const

function matchesFilter(category: string, filter: string) {
  if (filter === 'All Stories') return true
  if (filter === 'Ancient History') return category === 'History'
  if (filter === 'Oral Folklore') return category === 'Folklore'
  if (filter === 'Heritage Music') return category === 'Crafts' || category === 'Daily Life'
  return true
}

export default function ExploreMapPage() {
  const mapRef = useRef<JordanMapHandle>(null)
  const [activeFilter, setActiveFilter] = useState<(typeof filters)[number]>('All Stories')
  const [query, setQuery] = useState('')
  const [mapMode, setMapMode] = useState<'compass' | 'time' | 'heat'>('compass')
  const [focusedId, setFocusedId] = useState(
    stories.find((s) => s.id === 'echoes-of-petra')?.id ?? stories[0].id,
  )

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    return stories.filter((s) => {
      if (!matchesFilter(s.category, activeFilter)) return false
      if (!q) return true
      return (
        s.title.toLowerCase().includes(q) ||
        s.place.toLowerCase().includes(q) ||
        s.narrator.toLowerCase().includes(q) ||
        s.excerpt.toLowerCase().includes(q)
      )
    })
  }, [activeFilter, query])

  const focused = stories.find((s) => s.id === focusedId) ?? results[0] ?? stories[0]

  const visiblePins = useMemo(
    () => mapPins.filter((p) => results.some((s) => s.id === p.storyId)),
    [results],
  )

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col px-4 pb-0 pt-6 sm:px-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl">Explore Jordan</h1>
          <p className="text-sm text-muted">Discover {stories.length * 20} stories across the Kingdom</p>
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
            <span>Sort: Recent</span>
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
                <img
                  src={imageUrl(r.imageSeed, 100, 100, r.place)}
                  className="h-14 w-14 shrink-0 rounded-md object-cover"
                  alt=""
                />
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded-full bg-terracotta-light px-2 py-0.5 text-[9px] font-semibold uppercase text-terracotta-dark">
                      {r.category}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-muted">
                      <Clock size={10} /> {r.duration}
                    </span>
                  </div>
                  <div className="truncate text-[13px] font-medium">{r.title}</div>
                  <div className="truncate text-[11px] text-muted">{r.excerpt}</div>
                  <div className="mt-1 text-[10px] text-muted2">Narrated by {r.narrator}</div>
                </div>
              </button>
            ))}
            {results.length === 0 && (
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
            onSelectStory={setFocusedId}
            className="absolute inset-0"
          />

          <div className="pointer-events-none absolute right-4 top-4 z-10 w-52 rounded-xl bg-panel/95 px-4 py-3 text-[11px] shadow-sm">
            <div className="pointer-events-auto">
              <div className="mb-2 flex items-center justify-between font-semibold">
                Map legend <span className="h-1.5 w-1.5 rounded-full bg-teal" />
              </div>
              <div className="space-y-1.5 text-muted2">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-terracotta" /> Featured narratives
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full border border-gold bg-transparent" /> High
                  density zone
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
                <img
                  src={imageUrl(focused.imageSeed, 100, 100, focused.place)}
                  className="h-12 w-12 rounded-md object-cover"
                  alt=""
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[10px] uppercase text-muted">{focused.title}</div>
                  <div className="text-[11px] text-muted2">Narrated by {focused.narrator}</div>
                </div>
                <Link
                  to={`/story/${focused.id}`}
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
