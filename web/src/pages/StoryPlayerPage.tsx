import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bookmark, ChevronRight, Heart, MessageCircle, Pause, Play, Repeat, Share2, Shuffle,
  SkipBack, SkipForward, Volume2,
} from 'lucide-react'
import { Badge, Card, PillButton } from '../components/ui'
import { stories, transcript, upNext, reflections, imageUrl, avatarUrl } from '../data/mock'
import { galleryForPlace } from '../data/images'

const DURATION = 18 * 60 + 42 // 18:42 in seconds

function fmt(s: number) {
  const m = Math.floor(s / 60)
  const sec = String(Math.floor(s % 60)).padStart(2, '0')
  return `${m}:${sec}`
}

export default function StoryPlayerPage() {
  const { id } = useParams()
  const story = stories.find((s) => s.id === id) ?? stories.find((s) => s.id === 'echoes-of-jerash')!
  const [tab, setTab] = useState<'transcript' | 'accessibility'>('transcript')
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(6 * 60 + 34)
  const [saved, setSaved] = useState(true)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (playing) {
      timerRef.current = window.setInterval(() => {
        setElapsed((e) => (e >= DURATION ? (setPlaying(false), e) : e + 1))
      }, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [playing])

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4 text-sm">
        <div className="text-muted flex items-center gap-1.5">
          <Link to="/">Home</Link> <ChevronRight size={13} /> <Link to="/explore">Explore</Link> <ChevronRight size={13} /> <span className="text-ink">Story Player</span>
        </div>
        <div className="flex items-center gap-2">
          <PillButton variant="outline" className="!py-1.5 !px-3 text-xs"><Share2 size={13} /> Share</PillButton>
          <button
            onClick={() => setSaved((s) => !s)}
            className={`text-xs px-3 py-1.5 rounded-full border flex items-center gap-1.5 ${saved ? 'bg-terracotta-light text-terracotta-dark border-terracotta-light' : 'border-border text-muted2'}`}
          >
            <Bookmark size={13} fill={saved ? 'currentColor' : 'none'} /> {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_340px] gap-6">
        <div>
          <div className="relative h-72 rounded-xl2 overflow-hidden mb-4">
            <img src={imageUrl(story.imageSeed, 1000, 600, story.place)} className="w-full h-full object-cover" alt="" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
            <div className="absolute top-4 left-4 flex gap-2">
              <Badge tone="terracotta">Featured Legend</Badge>
              <Badge tone="teal">4K Spatial Audio</Badge>
            </div>
            <div className="absolute bottom-4 left-4 text-cream">
              <div className="font-serif text-2xl">{story.title}</div>
              <div className="text-xs text-cream/80 mt-1">{story.duration} · {story.place}, Jordan</div>
            </div>
          </div>

          {/* player bar */}
          <Card className="p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[11px] text-muted w-10">{fmt(elapsed)}</span>
              <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-terracotta to-gold" style={{ width: `${(elapsed / DURATION) * 100}%` }} />
              </div>
              <span className="text-[11px] text-muted w-10 text-right">{fmt(DURATION)}</span>
            </div>
            <div className="flex items-center justify-center gap-6 text-muted2">
              <Shuffle size={16} />
              <SkipBack size={18} />
              <button
                onClick={() => setPlaying((p) => !p)}
                className="w-11 h-11 rounded-full bg-terracotta text-cream flex items-center justify-center"
              >
                {playing ? <Pause size={18} /> : <Play size={18} />}
              </button>
              <SkipForward size={18} />
              <Repeat size={16} />
              <div className="flex items-center gap-1.5 ml-4">
                <Volume2 size={15} />
                <input type="range" defaultValue={70} className="w-16 accent-terracotta" />
              </div>
            </div>
          </Card>

          {galleryForPlace(story.place).length > 0 && (
            <div className="mb-6">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {story.place} gallery
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {galleryForPlace(story.place).map((src) => (
                  <img
                    key={src}
                    src={src}
                    alt={story.place}
                    className="h-24 w-36 shrink-0 rounded-lg border border-border object-cover"
                  />
                ))}
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-5 mb-8">
            <Card className="p-5">
              <div className="font-serif text-base mb-2">About this story</div>
              <p className="text-sm text-muted2 leading-relaxed mb-4">
                In this narrative, the storyteller recounts oral histories passed down through
                generations about life beneath the shadows of the ancient colonnades — and the
                whispers that still remain.
              </p>
              <div className="flex flex-wrap gap-2">
                {['#Roman History', '#Oral Heritage', '#Architecture'].map((t) => (
                  <span key={t} className="text-[11px] bg-gold-light text-gold px-2.5 py-1 rounded-full font-medium">{t}</span>
                ))}
              </div>
            </Card>
            <Card className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <img src={avatarUrl(story.narratorAvatarSeed, 80)} className="w-12 h-12 rounded-full object-cover" alt="" />
                <div>
                  <div className="text-sm font-semibold">{story.narrator}</div>
                  <div className="text-[11px] text-terracotta">Cultural Archivist</div>
                </div>
              </div>
              <p className="text-[13px] text-muted2 leading-relaxed mb-3">
                A lifelong resident dedicated to collecting oral histories from the elders of the
                Jordan Valley.
              </p>
              <PillButton variant="outline" className="w-full justify-center !py-2 text-xs">View full profile</PillButton>
            </Card>
          </div>

          {/* community reflections */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-serif text-xl">Community Reflections</h2>
            <PillButton variant="primary" className="!py-2 text-xs">Add your hikaya</PillButton>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            {reflections.map((c) => (
              <Card key={c.name} className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <img src={avatarUrl(c.avatarSeed, 60)} className="w-8 h-8 rounded-full object-cover" alt="" />
                  <div>
                    <div className="text-[12px] font-semibold">{c.name}</div>
                    <div className="text-[10px] text-muted">{c.timeAgo}</div>
                  </div>
                </div>
                <p className="text-[12.5px] italic text-ink2 mb-3">"{c.text}"</p>
                <div className="flex items-center gap-4 text-[11px] text-muted">
                  <span className="flex items-center gap-1"><Heart size={11} /> {c.likes}</span>
                  <span>Reply</span>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* right column */}
        <div>
          <Card className="p-1 mb-4">
            <div className="flex">
              {(['transcript', 'accessibility'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`flex-1 text-xs font-medium py-2.5 rounded-lg capitalize ${tab === t ? 'bg-cream text-ink' : 'text-muted'}`}
                >
                  {t}
                </button>
              ))}
            </div>
          </Card>

          {tab === 'transcript' ? (
            <div className="space-y-3 mb-4">
              {transcript.map((line) => (
                <div
                  key={line.time}
                  className={`text-[12.5px] leading-relaxed p-3 rounded-lg ${line.highlighted ? 'bg-terracotta-light border-l-2 border-terracotta text-ink2' : 'text-muted2'}`}
                >
                  <span className="font-mono text-[10px] text-terracotta mr-2">{line.time}</span>
                  {line.text}
                </div>
              ))}
            </div>
          ) : (
            <Card className="p-4 mb-4 text-[13px] text-muted2 leading-relaxed">
              This recording includes an auto-generated transcript and supports screen readers.
              A described-audio version noting visual scene changes is available on request.
            </Card>
          )}

          <div className="grid grid-cols-2 gap-3 mb-6">
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">1.2k</div>
              <div className="text-[11px] text-muted">Likes</div>
            </Card>
            <Card className="p-3 text-center">
              <div className="font-serif text-lg">84</div>
              <div className="text-[11px] text-muted">Comments</div>
            </Card>
          </div>

          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Up next</div>
            <span className="text-[11px] text-teal">Autoplay on</span>
          </div>
          <div className="space-y-2">
            {upNext.map((u) => (
              <Link to={`/story/${story.id}`} key={u.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-cream">
                <img src={imageUrl(u.imageSeed, 100, 100)} className="w-11 h-11 rounded-md object-cover" alt="" />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate">{u.title}</div>
                  <div className="text-[11px] text-muted">{u.author} · {u.duration}</div>
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
        <div>© 2024 Hikaya (حكاية) — Preserving Our Digital Silk Road.</div>
      </footer>
    </div>
  )
}
