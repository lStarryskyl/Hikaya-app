import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bookmark, Calendar, ChevronRight, Filter, Heart, MapPin, MessageCircle, MoreHorizontal,
  RotateCcw, Share2,
} from 'lucide-react'
import { Card, PillButton } from '../components/ui'
import { feedPosts, places, suggestedStorytellers, visitPlan, imageUrl, avatarUrl, placeCircleImage } from '../data/mock'

const tabs = ['For You', 'Following', 'Nearby'] as const

export default function CommunityFeedPage() {
  const [tab, setTab] = useState<(typeof tabs)[number]>('For You')
  const [posts, setPosts] = useState(feedPosts)

  function toggleLike(id: string) {
    setPosts((prev) =>
      prev.map((p) => (p.id === id ? { ...p, liked: !p.liked, likes: p.liked ? p.likes - 1 : p.likes + 1 } : p)),
    )
  }
  function toggleSave(id: string) {
    setPosts((prev) => prev.map((p) => (p.id === id ? { ...p, saved: !p.saved } : p)))
  }

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
            {places.map((p) => (
              <div key={p.name} className="flex flex-col items-center gap-1.5 shrink-0 w-16">
                <div className="w-14 h-14 rounded-full p-[2px]" style={{ background: 'conic-gradient(from 45deg,#B85C38,#C08A2E,#1F7A63,#B85C38)' }}>
                  <img src={placeCircleImage(p.name, 80)} className="w-full h-full rounded-full object-cover border-2 border-panel" alt="" />
                </div>
                <div className="text-[10px] font-semibold uppercase text-center leading-tight">{p.name}</div>
                <div className="text-[9px] text-muted -mt-0.5">{p.person}</div>
              </div>
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
            {posts.map((post) => (
              <Card key={post.id} className="overflow-hidden">
                <div className="flex items-center gap-3 p-3.5">
                  <img src={avatarUrl(post.avatarSeed, 60)} className="w-9 h-9 rounded-full object-cover" alt="" />
                  <div className="flex-1">
                    <div className="text-[13px] font-semibold">{post.name}</div>
                    <div className="text-[11px] text-muted flex items-center gap-1"><MapPin size={10} /> {post.place}</div>
                  </div>
                  <MoreHorizontal size={16} className="text-muted" />
                </div>
                <img src={imageUrl(post.imageSeed, 900, 620, post.place)} className="w-full h-80 object-cover" alt="" />
                <div className="flex items-center gap-4 px-4 pt-3 text-ink2">
                  <button onClick={() => toggleLike(post.id)}>
                    <Heart size={20} className={post.liked ? 'text-terracotta' : ''} fill={post.liked ? 'currentColor' : 'none'} />
                  </button>
                  <MessageCircle size={20} />
                  <Share2 size={20} />
                  <button onClick={() => toggleSave(post.id)} className="ml-auto">
                    <Bookmark size={20} className={post.saved ? 'text-terracotta' : ''} fill={post.saved ? 'currentColor' : 'none'} />
                  </button>
                </div>
                <div className="px-4 pt-2 text-[13px] font-semibold">{post.likes.toLocaleString()} likes</div>
                <div className="px-4 pt-1 pb-1 text-[13px] leading-relaxed">
                  <span className="font-semibold">@{post.name.toLowerCase().replace(/\s+/g, '_')}</span> {post.caption}
                </div>
                <div className="px-4 text-[12px] text-muted">View all {post.comments} comments</div>
                <div className="px-4 pb-4 pt-1 text-[11px] text-muted">{post.timeAgo}</div>
              </Card>
            ))}
          </div>

          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <div className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted">
              <RotateCcw size={16} />
            </div>
            <div className="font-serif text-base">You're all caught up</div>
            <p className="text-[12px] text-muted">You've seen all new stories from the past 48 hours.</p>
            <PillButton variant="outline" className="text-xs">Load older stories</PillButton>
          </div>
        </div>

        {/* right rail */}
        <div className="space-y-5">
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-semibold flex items-center gap-1.5"><Calendar size={13} /> Visit planner</div>
              <span className="text-[10px] bg-terracotta-light text-terracotta-dark px-2 py-0.5 rounded-full font-semibold">Next 2 days</span>
            </div>
            <div className="space-y-3 mb-3">
              {visitPlan.map((v) => (
                <div key={v.title} className="border-l-2 border-terracotta pl-3">
                  <div className="text-[12.5px] font-medium">{v.title}</div>
                  <div className="text-[11px] text-muted">{v.date} · {v.who}</div>
                </div>
              ))}
            </div>
            <PillButton variant="outline" className="w-full justify-center text-xs">Plan new exploration</PillButton>
          </Card>

          <Card className="overflow-hidden">
            <div className="relative h-28">
              <img src={imageUrl('nabataean-water-channels', 400, 240)} className="w-full h-full object-cover" alt="" />
              <span className="absolute top-2 left-2 text-[9px] font-semibold bg-terracotta text-cream px-2 py-1 rounded-full">Editor's pick</span>
            </div>
            <div className="p-3.5">
              <div className="text-[13px] font-serif mb-1">Secrets of the Nabateans</div>
              <p className="text-[11px] text-muted-2 text-muted leading-relaxed mb-2">
                Explore the hidden water channels and carved dwellings away from the main Siq trail.
              </p>
              <div className="flex items-center justify-between">
                <div className="flex -space-x-2">
                  {['a', 'b', 'c'].map((s) => (
                    <img key={s} src={avatarUrl('viewer-' + s, 40)} className="w-5 h-5 rounded-full border-2 border-panel object-cover" alt="" />
                  ))}
                </div>
                <Link to="/explore" className="text-[11px] text-terracotta font-medium">View map</Link>
              </div>
            </div>
          </Card>

          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-semibold">Suggested storytellers</div>
              <span className="text-[10px] font-medium text-terracotta">See all</span>
            </div>
            <div className="space-y-3">
              {suggestedStorytellers.map((s) => (
                <div key={s.handle} className="flex items-center gap-2.5">
                  <img
                    src={avatarUrl(s.seed, 60)}
                    className="h-8 w-8 rounded-full object-cover"
                    alt=""
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-medium">{s.name}</div>
                    <div className="truncate text-[10.5px] text-muted">{s.handle}</div>
                  </div>
                  <button className="rounded-full border border-terracotta-light px-2.5 py-1 text-[11px] font-semibold text-terracotta">
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
              <span>Locations</span>
              <span>Language</span>
            </div>
            <div>© 2024 HIKAYA PLATFORM</div>
          </div>
        </div>
      </div>
    </div>
  )
}
