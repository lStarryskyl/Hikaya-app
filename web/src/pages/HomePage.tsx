import { Link } from 'react-router-dom'
import { ArrowRight, Heart, Mic, Play, Share2, Sparkles } from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import JordanMap from '../components/JordanMap'
import Photo from '../components/Photo'
import { initials } from '../auth'
import { findPhoto, getFeed, getPins, getPlaces } from '../discover'
import { CATEGORY_LABELS, formatDuration, type CategoryValue } from '../stories'
import { toMapPins } from '../types'
import { useApi } from '../useApi'

const badgeTone: Record<CategoryValue, 'terracotta' | 'gold' | 'teal'> = {
  crafts: 'gold',
  daily_life: 'terracotta',
  folklore: 'teal',
  history: 'terracotta',
  personal: 'gold',
}

export default function HomePage() {
  const feed = useApi(() => getFeed({ limit: 50 }), [])
  const museum = useApi(() => getFeed({ curated: true, limit: 50 }), [])
  const pins = useApi(getPins, [])
  const places = useApi(getPlaces, [])

  const stories = feed.data?.items ?? []
  // The featured row is the museum: stories staff have curated, newest first.
  const featured = (museum.data?.items ?? []).slice(0, 3)
  const recentCount = (pins.data ?? []).filter((p) => p.kind === 'recent').length
  const hero = findPhoto(places.data, 'petra-treasury-hero') ?? places.data?.[0]?.cover
  const stats = [
    { label: 'Stories told', value: stories.length || '…' },
    { label: 'Places', value: places.data?.length || '…' },
    { label: 'In the museum', value: museum.data ? museum.data.items.length : '…' },
  ]

  return (
    <div className="pb-16">
      <section className="relative mx-4 mt-5 overflow-hidden rounded-xl2 border border-border sm:mx-6 sm:mt-6">
        <Photo
          photo={hero}
          width={1600}
          sizes="100vw"
          className="absolute inset-0 h-full w-full object-cover sepia-[.15] saturate-[.85]"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/40 to-black/10" />
        <div className="relative max-w-xl px-6 py-12 text-cream sm:px-10 sm:py-16">
          <div className="mb-4 flex items-center gap-2 text-[11px] uppercase tracking-wider text-terracotta-light">
            <span className="h-px w-4 bg-terracotta-light" /> Preserving our echoes
          </div>
          <h1 className="mb-4 font-serif text-3xl leading-tight sm:text-4xl">
            Every place has a voice.
            <br />
            <span className="italic text-terracotta-light">Give yours to Jordan.</span>
          </h1>
          <p className="mb-7 max-w-md text-sm leading-relaxed text-cream/85">
            Join a community of travelers and locals documenting the hidden narratives of the
            Levant. Record your journey, or wander through the stories of others.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link to="/create">
              <PillButton variant="primary">
                <Mic size={15} /> Record a story
              </PillButton>
            </Link>
            <Link to={featured[0] ? `/story/${featured[0].id}` : '/explore'}>
              <PillButton
                variant="outline"
                className="!border-cream/40 !text-cream hover:!bg-white/10"
              >
                <Play size={15} /> Watch a story
              </PillButton>
            </Link>
          </div>
        </div>
        <div className="relative m-4 flex w-fit gap-6 rounded-xl2 bg-panel/95 px-5 py-3.5 sm:absolute sm:bottom-8 sm:right-8 sm:m-0 sm:gap-8 sm:px-6 sm:py-4">
          {stats.map((s) => (
            <div key={s.label}>
              <div className="text-[10px] uppercase tracking-wide text-muted">{s.label}</div>
              <div className="font-serif text-lg">{s.value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-12 px-4 sm:px-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="mb-1 font-serif text-2xl">Voice of the Week</h2>
            <p className="max-w-xl text-sm text-muted2">
              Curated narratives from across the kingdom, from the weaving looms of Madaba to the
              sunset dunes of Wadi Rum.
            </p>
          </div>
          <Link
            to="/explore"
            className="inline-flex items-center gap-1 whitespace-nowrap text-sm font-medium text-terracotta"
          >
            Explore all stories <ArrowRight size={14} />
          </Link>
        </div>

        {museum.error && <p className="text-sm text-terracotta-dark">{museum.error}</p>}
        {museum.data && featured.length === 0 && (
          <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted2">
            No stories are in the museum yet. <Link to="/explore" className="text-terracotta hover:underline">Explore all stories</Link>
          </p>
        )}
        <div className="grid gap-5 md:grid-cols-3">
          {featured.map((s) => (
            <Card key={s.id} className="h-full overflow-hidden transition-shadow hover:shadow-md">
              <Link to={`/story/${s.id}`} className="block">
                <div className="relative h-40">
                  <Photo
                    photo={s.cover}
                    width={500}
                    sizes="(min-width: 768px) 33vw, 100vw"
                    className="h-full w-full object-cover sepia-[.1]"
                  />
                  <div className="absolute left-3 top-3 flex gap-1.5">
                    {s.category && <Badge tone={badgeTone[s.category]}>{CATEGORY_LABELS[s.category]}</Badge>}
                    {s.curated && <Badge tone="teal">Curated</Badge>}
                  </div>
                  <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-black/60 px-2 py-1 text-[10px] text-cream">
                    <Play size={10} /> {formatDuration(s.duration_ms)}
                  </div>
                </div>
              </Link>
              <div className="p-4">
                <div className="mb-1 text-[11px] text-muted">@ {s.place_name.toUpperCase()}</div>
                <Link
                  to={`/story/${s.id}`}
                  className="mb-3 block font-serif text-[15px] text-ink hover:text-terracotta"
                >
                  {s.title}
                </Link>
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-terracotta-light text-[8px] font-semibold text-terracotta-dark">
                    {initials(s.author.display_name)}
                  </span>
                  <span className="flex-1 text-[12px] text-muted2">{s.author.display_name}</span>
                  <button type="button" className="text-muted hover:text-terracotta" aria-label="Like">
                    <Heart size={14} />
                  </button>
                  <button type="button" className="text-muted hover:text-ink" aria-label="Share">
                    <Share2 size={14} />
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-14 grid items-center gap-10 px-4 md:grid-cols-2 sm:px-8">
        <div>
          <Badge tone="gold">Spatial Archive</Badge>
          <h2 className="mb-3 mt-4 font-serif text-2xl">Listen as you Wander</h2>
          <p className="mb-4 max-w-md text-sm leading-relaxed text-muted2">
            Our interactive map pairs geographical coordinates with cultural memories. Discover
            localized folklore, oral histories, and environmental recordings pinned to the exact
            spots they originated.
          </p>
          <ul className="mb-6 space-y-2">
            {[
              'audio-guided heritage trails',
              'crowdsourced cultural markers',
              'real-time location discovery',
            ].map((t) => (
              <li key={t} className="flex items-center gap-2 text-sm font-medium text-ink2">
                <span className="h-1.5 w-1.5 rounded-full bg-teal" /> {t}
              </li>
            ))}
          </ul>
          <Link to="/explore">
            <PillButton variant="primary">
              Open interactive map <ArrowRight size={14} />
            </PillButton>
          </Link>
        </div>

        <div className="relative h-72 overflow-hidden rounded-xl2 border border-border">
          <JordanMap
            pins={toMapPins(pins.data ?? [])}
            interactive={false}
            zoom={6.2}
            flyToFocused={false}
            className="absolute inset-0"
          />
          <Link
            to="/explore"
            className="absolute inset-0 z-10 flex items-end p-4 no-underline"
            aria-label="Open interactive map"
          >
            <div className="flex w-full items-center gap-3 rounded-xl bg-panel/95 px-4 py-3 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-terracotta text-[11px] font-semibold text-cream">
                ●
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted">Live map preview</div>
                <div className="text-sm font-medium text-ink">
                  {pins.data
                    ? `${pins.data.length} stories on the map · ${recentCount} added in the last two weeks`
                    : 'Loading the map…'}
                </div>
              </div>
            </div>
          </Link>
        </div>
      </section>

      <section className="mt-14 px-4 sm:px-8">
        <Card className="relative overflow-hidden px-6 py-14 text-center sm:px-10">
          <Sparkles size={70} className="absolute right-8 top-6 text-border" />
          <h2 className="mb-3 font-serif text-2xl">Be the Voice of Your Village</h2>
          <p className="mx-auto mb-7 max-w-lg text-sm leading-relaxed text-muted2">
            History isn't just in books; it's in the way we brew coffee, the stories our
            grandmothers told us, and the names we give the mountains. Contribute to the
            collective memory.
          </p>
          <div className="mb-8 flex items-center justify-center gap-6">
            <Link to="/create">
              <PillButton variant="primary">Start recording</PillButton>
            </Link>
            <Link to="/feed" className="text-sm font-medium text-ink2">
              Browse latest
            </Link>
          </div>
          <div className="flex items-center justify-center gap-2">
            {['#F3E2D6', '#F1E5C9', '#DCEFE7', '#D9D2C4', '#E9C3B4'].map((c, i) => (
              <span
                key={i}
                className="inline-block h-7 w-7 rounded-full border border-border"
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </Card>
      </section>

      <footer className="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 pt-6 text-[12px] text-muted sm:px-8">
        <div>
          <div className="font-arabic text-ink2">Hikaya | حكاية</div>
          <div>Cultural Heritage &amp; Community Storytelling Archive</div>
        </div>
        <div className="flex gap-5">
          <span>about</span>
          <span>partners</span>
          <span>archive policy</span>
          <span>contact</span>
        </div>
        <div>© {new Date().getFullYear()} Hikaya Platform, Jordan.</div>
      </footer>
    </div>
  )
}
