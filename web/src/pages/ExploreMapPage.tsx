import { t, useLocale, message, number } from '../i18n'
import { Component, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MapPin, Navigation, Search, ZoomIn, ZoomOut } from 'lucide-react'
import { Badge, Card } from '../components/ui'
import JordanMap, { type JordanMapHandle } from '../components/JordanMap'
import Photo from '../components/Photo'
import { type DiscoveryFilters, type StoryCard } from '../discover'
import { CATEGORY_LABELS, formatDuration, getStory, type CategoryValue } from '../stories'
import { toMapPins } from '../types'
import { useDebounced, useDiscovery, useNearby } from '../useDiscovery'

class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <p role="status" className="p-6">
        {t('The map is unavailable. You can still browse and open stories from the list.')}
      </p>
    ) : (
      this.props.children
    )
  }
}

export default function ExploreMapPage() {
  useLocale()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const tag = params.get('tag') ?? ''
  const category = params.get('category') ?? ''
  const curated = params.get('curated') === 'true'
  const debouncedQuery = useDebounced(query)
  const debouncedTag = useDebounced(tag)
  const nearby = useNearby()
  const [radius, setRadius] = useState(25)
  const filters: DiscoveryFilters = {
    q: debouncedQuery,
    tag: debouncedTag.trim() ? [debouncedTag.trim()] : [],
    category: Object.prototype.hasOwnProperty.call(CATEGORY_LABELS, category)
      ? [category as CategoryValue]
      : [],
    curated,
    ...(nearby.position ? { ...nearby.position, radius_km: radius } : {}),
  }
  const search = useDiscovery(filters)
  const results = search.page?.items ?? []
  const mapRef = useRef<JordanMapHandle>(null)
  const [selected, setSelected] = useState<StoryCard | null>(null)
  const [selectionError, setSelectionError] = useState('')
  const selectionGeneration = useRef(0)
  const filterKey = JSON.stringify(filters)
  const requestNearby = nearby.request
  const requestedOnArrival = useRef(false)
  useEffect(() => {
    if (params.get('nearby') === '1' && !requestedOnArrival.current) {
      requestedOnArrival.current = true
      requestNearby()
    }
  }, [params, requestNearby])
  useEffect(() => {
    selectionGeneration.current++
    setSelected(null)
    setSelectionError('')
    return () => {
      selectionGeneration.current++
    }
  }, [filterKey])
  const focused = selected ?? results[0] ?? null

  function update(name: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        if (value) next.set(name, value)
        else next.delete(name)
        return next
      },
      { replace: name === 'q' || name === 'tag' },
    )
  }
  async function selectStory(id: string) {
    const current = ++selectionGeneration.current
    setSelectionError('')
    const loaded = results.find((story) => story.id === id)
    if (loaded) {
      setSelected(loaded)
      return
    }
    try {
      const story = await getStory(id)
      if (current !== selectionGeneration.current) return
      setSelected({
        ...story,
        excerpt: story.layers[0]?.segments[0]?.text ?? '',
        distance_km: null,
      })
    } catch {
      if (current === selectionGeneration.current)
        setSelectionError('This story could not be opened. Try selecting it again.')
    }
  }

  return (
    <div className="px-4 py-6 sm:px-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl">{t('Explore Jordan')}</h1>
          <p className="text-sm text-muted2">{t('Find the voices and memories of a place.')}</p>
        </div>
        <button
          type="button"
          onClick={nearby.request}
          disabled={nearby.loading}
          className="inline-flex items-center gap-2 rounded-full bg-terracotta px-4 py-2 text-sm text-cream disabled:opacity-60"
        >
          <Navigation size={16} />
          {nearby.loading ? t('Finding your location…') : t('Explore near me')}
        </button>
      </div>
      <form
        role="search"
        onSubmit={(event) => event.preventDefault()}
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        <label className="text-sm">
          {t('Search stories')}
          <span className="mt-1 flex items-center gap-2 rounded-lg border border-border bg-panel px-3 py-2">
            <Search size={16} aria-hidden />
            <input
              aria-label={t('Filter stories')}
              value={query}
              maxLength={200}
              onChange={(e) => update('q', e.target.value)}
              placeholder={t('Story, place or storyteller')}
              className="min-w-0 flex-1 bg-transparent"
            />
          </span>
        </label>
        <label className="text-sm">
          {t('Category')}
          <select
            value={category}
            onChange={(e) => update('category', e.target.value)}
            className="mt-1 block w-full rounded-lg border border-border bg-panel px-3 py-2"
          >
            <option value="">{t('All categories')}</option>
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {t('Tag')}
          <input
            value={tag}
            maxLength={40}
            onChange={(e) => update('tag', e.target.value)}
            placeholder={t('e.g. weaving')}
            className="mt-1 block w-full rounded-lg border border-border bg-panel px-3 py-2"
          />
        </label>
        <div className="flex items-end gap-3 pb-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={curated}
              onChange={(e) => update('curated', e.target.checked ? 'true' : '')}
            />
            {t('Museum')}
          </label>
          <button
            type="button"
            onClick={() => {
              setParams({})
              nearby.clear()
              setRadius(25)
            }}
            className="text-sm text-terracotta-dark underline"
          >
            {t('Clear filters')}
          </button>
        </div>
      </form>
      {nearby.error && (
        <p
          role="status"
          className="mb-4 rounded-lg bg-terracotta-light p-3 text-sm text-terracotta-dark"
        >
          {t(nearby.error)}
        </p>
      )}
      {nearby.position && (
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
          <label>
            {t('Search radius')}{' '}
            <select
              aria-label={t('Search radius')}
              value={radius}
              onChange={(e) => setRadius(Number(e.target.value))}
              className="rounded-lg border border-border bg-panel p-2"
            >
              {[5, 10, 25, 50, 100, 250, 500].map((km) => (
                <option key={km} value={km}>
                  {km} {t('km')}
                </option>
              ))}
            </select>
          </label>
          <span>{t('Using your approximate location for this search.')}</span>
          <button
            type="button"
            onClick={() => {
              nearby.clear()
              update('nearby', '')
            }}
            className="text-terracotta-dark underline"
          >
            {t('Leave nearby mode')}
          </button>
        </div>
      )}
      <p role="status" aria-live="polite" className="mb-3 text-sm text-muted2">
        {search.loading && !search.page
          ? t('Loading stories…')
          : message('{count} stories found', { count: number(search.page?.total ?? 0) })}
        {nearby.position ? t(' · Nearest first') : t(' · Newest first')}
      </p>
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card className="max-h-[70vh] overflow-y-auto p-3">
          <div aria-busy={search.loading} className="space-y-3">
            {search.loading &&
              !search.page &&
              [1, 2, 3].map((n) => (
                <div key={n} aria-hidden className="h-24 animate-pulse rounded-xl bg-cream" />
              ))}
            {results.map((story) => (
              <article
                key={story.id}
                className={`rounded-xl border p-3 ${focused?.id === story.id ? 'border-terracotta bg-terracotta-light/30' : 'border-border'}`}
              >
                <button
                  type="button"
                  onClick={() => void selectStory(story.id)}
                  aria-pressed={focused?.id === story.id}
                  className="flex w-full gap-3 text-start"
                >
                  <Photo
                    photo={story.cover}
                    width={112}
                    className="h-16 w-16 shrink-0 rounded-lg object-cover"
                  />
                  <span className="min-w-0">
                    <span dir="auto" className="block font-medium">
                      {story.title}
                    </span>
                    <span className="block text-xs text-muted2">
                      {story.place_name} · {story.author.display_name}
                    </span>
                  </span>
                </button>
                <p dir="auto" className="my-2 line-clamp-2 text-xs text-muted2">
                  {story.excerpt}
                </p>
                <div className="mb-2 flex flex-wrap gap-1">
                  {story.curated && <Badge tone="teal">{t('Curated')}</Badge>}
                  {story.tags?.map((value) => (
                    <button
                      type="button"
                      key={value}
                      onClick={() => update('tag', value)}
                      className="rounded-full bg-cream px-2 py-1 text-xs"
                    >
                      #{value}
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span>
                    {story.distance_km != null
                      ? message('{distance} km away', {
                          distance: number(story.distance_km, { maximumFractionDigits: 1 }),
                        })
                      : formatDuration(story.duration_ms)}
                  </span>
                  <Link
                    className="font-medium text-terracotta-dark underline"
                    to={`/story/${story.id}`}
                  >
                    {t('Listen to story')}
                  </Link>
                </div>
              </article>
            ))}
            {!search.loading && !search.error && results.length === 0 && (
              <div className="p-6 text-center">
                <p>{t('No stories match these filters.')}</p>
                <p className="mt-2 text-sm text-muted2">
                  {t('Try a different place or tag, clear filters, or widen the nearby radius.')}
                </p>
              </div>
            )}
            {search.error && (
              <div role="alert" className="p-3 text-sm text-terracotta-dark">
                <p>{t(search.error)}</p>
                <button
                  type="button"
                  onClick={search.page ? () => void search.loadMore() : search.retry}
                  className="mt-2 underline"
                >
                  {t('Try again')}
                </button>
              </div>
            )}
            {search.page?.next_cursor && (
              <button
                type="button"
                disabled={search.loading}
                onClick={() => void search.loadMore()}
                className="w-full rounded-full border border-border p-3 text-sm"
              >
                {search.loading ? t('Loading…') : t('Load more stories')}
              </button>
            )}
          </div>
        </Card>
        <Card className="relative min-h-[480px] overflow-hidden">
          <MapBoundary>
            <JordanMap
              ref={mapRef}
              pins={toMapPins(search.pins)}
              focusedStoryId={focused?.id}
              onSelectStory={(id) => void selectStory(id)}
              className="absolute inset-0"
            />
          </MapBoundary>
          <div className="absolute end-4 top-4 flex flex-col gap-2">
            <button
              type="button"
              aria-label={t('Zoom in')}
              onClick={() => mapRef.current?.zoomIn()}
              className="rounded-lg bg-panel p-3 shadow"
            >
              <ZoomIn size={16} />
            </button>
            <button
              type="button"
              aria-label={t('Zoom out')}
              onClick={() => mapRef.current?.zoomOut()}
              className="rounded-lg bg-panel p-3 shadow"
            >
              <ZoomOut size={16} />
            </button>
          </div>
          {focused && (
            <div className="absolute bottom-4 start-4 end-4 rounded-xl bg-panel p-4 shadow">
              <p className="mb-1 flex items-center gap-1 text-xs text-muted2">
                <MapPin size={12} />
                {focused.place_name}
              </p>
              <Link
                dir="auto"
                to={`/story/${focused.id}`}
                className="font-serif text-lg text-terracotta-dark underline"
              >
                {focused.title}
              </Link>
              <p className="text-xs text-muted2">
                {t('Told by')} {focused.author.display_name}
              </p>
            </div>
          )}
          {selectionError && (
            <p
              role="alert"
              className="absolute top-4 start-4 max-w-xs rounded-lg bg-panel p-3 text-sm"
            >
              {t(selectionError)}
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}
