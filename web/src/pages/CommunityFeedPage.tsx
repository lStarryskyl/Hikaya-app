import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bookmark, Calendar, ChevronRight, Filter, Heart, MapPin, MessageCircle, MoreHorizontal,
  RotateCcw, Share2,
} from 'lucide-react'
import { Card, PillButton } from '../components/ui'
import Photo from '../components/Photo'
import { ApiError } from '../api'
import { initials } from '../auth'
import { getFeed, getPlaces, timeAgo, type StoryCard } from '../discover'
import { engagementFor, exampleVisitPlan } from '../demo/mockEngagement'
import { useApi } from '../useApi'

const tabs = ['For You', 'Following', 'Nearby'] as const
const PAGE_SIZE = 5

/** Likes and saves are mock: they live in this page's state only and are never stored. */
type MockReaction = { liked: boolean; saved: boolean }

export default function CommunityFeedPage() {
  const [tab, setTab] = useState<(typeof tabs)[number]>('For You')
  const [stories, setStories] = useState<StoryCard[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reactions, setReactions] = useState<Record<string, MockReaction>>({})
  const places = useApi(getPlaces, [])

  async function loadMore(from: string | null) {
    setLoading(true)
    setError('')
    try {
      const page = await getFeed({ limit: PAGE_SIZE, cursor: from })
      setStories((prev) => [...prev, ...page.items.filter((s) => !prev.some((p) => p.id === s.id))])
      setCursor(page.next_cursor)
      setDone(page.next_cursor === null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load stories.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadMore(null)
  }, [])

  function react(id: string, key: keyof MockReaction) {
    setReactions((r) => {
      const current = r[id] ?? { liked: false, saved: false }
      return { ...r, [id]: { ...current, [key]: !current[key] } }
    })
  }

  const pick = stories.find((s) => s.curated)
  const storytellers = [...new Map(stories.map((s) => [s.author.id, s.author])).values()].slice(0, 3)

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto">
      <div className="text-[12px] text-muted mb-1 flex items-center gap-1.5">
        Jordan <ChevronRight size={12} /> Heritage <ChevronRight size={12} /> Live Stories
      </div>
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h1 className="font-serif text-2xl">Community Feed</h1>
        <div className="flex gap-2">
          <PillButton variant="outline" className="!py-2 text-xs"><Filter size={13} /> Filters</PillButton>
          <PillButton variant="primary" className="!py-2 text-xs"><MapPin size={13} /> Explore near me</PillButton>
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_300px] gap-6">
        <div>
          <div className="flex gap-4 overflow-x-auto pb-4 mb-2 border-b border-border scrollbar-thin">
            {(places.data ?? []).map((p) => (
              <Link
                key={p.slug}
                to="/explore"
                className="flex flex-col items-center gap-1.5 shrink-0 w-16 no-underline"
              >
                <div className="w-14 h-14 rounded-full p-[2px]" style={{ background: 'conic-gradient(from 45deg,#B85C38,#C08A2E,#1F7A63,#B85C38)' }}>
                  <Photo photo={p.cover} width={112} className="w-full h-full rounded-full object-cover border-2 border-panel" />
                </div>
                <div className="text-[10px] font-semibold uppercase text-center leading-tight text-ink">{p.name}</div>
                <div className="text-[9px] text-muted -mt-0.5">
                  {p.story_count} {p.story_count === 1 ? 'story' : 'stories'}
                </div>
              </Link>
            ))}
          </div>

          <div className="flex gap-5 mb-5 text-sm">
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`pb-2 border-b-2 ${tab === t ? 'border-terracotta text-terracotta font-semibold' : 'border-transparent text-muted'}`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="space-y-6">
            {stories.map((story) => {
              const mock = engagementFor(story.id)
              const mine = reactions[story.id] ?? { liked: false, saved: false }
              return (
                <Card key={story.id} className="overflow-hidden">
                  <div className="flex items-center gap-3 p-3.5">
                    <span className="flex w-9 h-9 items-center justify-center rounded-full bg-terracotta-light text-xs font-semibold text-terracotta-dark">
                      {initials(story.author.display_name)}
                    </span>
                    <div className="flex-1">
                      <div className="text-[13px] font-semibold">{story.author.display_name}</div>
                      <div className="text-[11px] text-muted flex items-center gap-1"><MapPin size={10} /> {story.place_name}, Jordan</div>
                    </div>
                    <MoreHorizontal size={16} className="text-muted" aria-hidden />
                  </div>
                  <Link to={`/story/${story.id}`} className="block" aria-label={`Open ${story.title}`}>
                    <Photo photo={story.cover} width={900} sizes="(min-width: 1024px) 640px, 100vw" className="w-full h-80 object-cover" />
                  </Link>
                  <div className="flex items-center gap-4 px-4 pt-3 text-ink2">
                    <button type="button" onClick={() => react(story.id, 'liked')} aria-pressed={mine.liked} aria-label="Like">
                      <Heart size={20} className={mine.liked ? 'text-terracotta' : ''} fill={mine.liked ? 'currentColor' : 'none'} />
                    </button>
                    <Link to={`/story/${story.id}`} aria-label="Comments"><MessageCircle size={20} /></Link>
                    <Share2 size={20} aria-hidden />
                    <button type="button" onClick={() => react(story.id, 'saved')} aria-pressed={mine.saved} aria-label="Save" className="ml-auto">
                      <Bookmark size={20} className={mine.saved ? 'text-terracotta' : ''} fill={mine.saved ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                  <div className="px-4 pt-2 text-[13px] font-semibold">
                    {(mock.likes + (mine.liked ? 1 : 0)).toLocaleString()} likes
                  </div>
                  <div className="px-4 pt-1 pb-1 text-[13px] leading-relaxed">
                    <Link to={`/story/${story.id}`} className="font-semibold text-ink">{story.title}</Link>{' '}
                    {story.excerpt}
                  </div>
                  <div className="px-4 text-[12px] text-muted">View all {mock.comments} comments</div>
                  <div className="px-4 pb-4 pt-1 text-[11px] text-muted">{timeAgo(story.published_at)}</div>
                </Card>
              )
            })}
          </div>

          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <div className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted">
              <RotateCcw size={16} />
            </div>
            {error ? (
              <p role="alert" className="text-[12px] text-terracotta-dark">{error}</p>
            ) : done ? (
              <>
                <div className="font-serif text-base">You're all caught up</div>
                <p className="text-[12px] text-muted">You've seen every story on Hikaya so far.</p>
              </>
            ) : null}
            {!done && (
              <PillButton
                variant="outline"
                className="text-xs disabled:opacity-60"
                disabled={loading}
                onClick={() => void loadMore(cursor)}
              >
                {loading ? 'Loading…' : 'Load older stories'}
              </PillButton>
            )}
          </div>
        </div>

        {/* right rail */}
        <div className="space-y-5">
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-semibold flex items-center gap-1.5"><Calendar size={13} /> Visit planner</div>
              <span className="text-[10px] bg-terracotta-light text-terracotta-dark px-2 py-0.5 rounded-full font-semibold">Example</span>
            </div>
            <div className="space-y-3 mb-3">
              {exampleVisitPlan().map((v) => (
                <div key={v.title} className="border-l-2 border-terracotta pl-3">
                  <div className="text-[12.5px] font-medium">{v.title}</div>
                  <div className="text-[11px] text-muted">{v.date}</div>
                </div>
              ))}
            </div>
            <p className="text-[10.5px] text-muted">Visit planning is coming later.</p>
          </Card>

          {pick && (
            <Card className="overflow-hidden">
              <div className="relative h-28">
                <Photo photo={pick.cover} width={400} className="w-full h-full object-cover" />
                <span className="absolute top-2 left-2 text-[9px] font-semibold bg-terracotta text-cream px-2 py-1 rounded-full">Editor's pick</span>
              </div>
              <div className="p-3.5">
                <div className="text-[13px] font-serif mb-1">{pick.title}</div>
                <p className="text-[11px] text-muted leading-relaxed mb-2">{pick.excerpt}</p>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted">{pick.place_name}</span>
                  <Link to={`/story/${pick.id}`} className="text-[11px] text-terracotta font-medium">Listen</Link>
                </div>
              </div>
            </Card>
          )}

          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-semibold">Storytellers</div>
            </div>
            <div className="space-y-3">
              {storytellers.map((s) => (
                <div key={s.id} className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-terracotta-light text-[11px] font-semibold text-terracotta-dark">
                    {initials(s.display_name)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-medium">{s.display_name}</div>
                  </div>
                  {/* Following is mock in the demo. */}
                  <button type="button" className="rounded-full border border-terracotta-light px-2.5 py-1 text-[11px] font-semibold text-terracotta">
                    Follow
                  </button>
                </div>
              ))}
            </div>
          </Card>

          <div className="px-1 text-[10px] leading-relaxed text-muted">
            <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
              <span>About</span>
              <span>Help</span>
              <span>Privacy</span>
              <span>Terms</span>
            </div>
            <div>© {new Date().getFullYear()} HIKAYA PLATFORM</div>
          </div>
        </div>
      </div>
    </div>
  )
}
