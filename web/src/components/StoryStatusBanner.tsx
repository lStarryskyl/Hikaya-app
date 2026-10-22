import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Clock, FilePen, Loader2 } from 'lucide-react'
import { MODERATION_LABELS, getStory, type StoryRecord } from '../stories'

const POLL_MS = 2000

/**
 * What the author sees on their own story while it is not published: being checked,
 * under review (and why), or sent back with the reviewer's note.
 */
export default function StoryStatusBanner({
  story,
  onChange,
}: {
  story: StoryRecord
  onChange: (story: StoryRecord) => void
}) {
  // While the check runs, look again every few seconds until the result is in.
  useEffect(() => {
    if (story.status !== 'moderating') return
    let stopped = false
    const timer = window.setInterval(async () => {
      try {
        const fresh = await getStory(story.id)
        if (!stopped && fresh.status !== 'moderating') onChange(fresh)
      } catch {
        /* keep the current banner; the next tick tries again */
      }
    }, POLL_MS)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [story.id, story.status, onChange])

  if (story.status === 'published') return null

  const raised = story.moderation?.labels.filter((l) => l.raised) ?? []
  const editLink = (
    <Link to={`/create?story=${story.id}`} className="font-semibold text-terracotta hover:underline">
      Edit and resubmit
    </Link>
  )

  const content = {
    draft: {
      icon: <FilePen size={16} />,
      title: 'This story is a draft',
      body: (
        <>
          Only you can see it. <Link to={`/create?story=${story.id}`} className="font-semibold text-terracotta hover:underline">Continue editing</Link>
        </>
      ),
    },
    moderating: {
      icon: <Loader2 size={16} className="animate-spin" />,
      title: 'We are checking your story',
      body: 'It will be published in a moment if nothing needs a closer look.',
    },
    held: {
      icon: <Clock size={16} />,
      title: 'Your story is under review',
      body: (
        <>
          Our automatic check asked a reviewer to read it before it is published.
          {raised.length > 0 && (
            <ul className="mt-2 list-disc ps-5">
              {raised.map((l) => (
                <li key={l.label}>
                  <span className="font-medium">{MODERATION_LABELS[l.label]}</span>
                  {l.reason && `: ${l.reason}`}
                </li>
              ))}
            </ul>
          )}
        </>
      ),
    },
    needs_edit: {
      icon: <AlertTriangle size={16} />,
      title: 'A reviewer asked for changes',
      body: (
        <>
          {story.review?.note ? <q className="block italic">{story.review.note}</q> : 'Please review your story.'}
          <div className="mt-2">{editLink}</div>
        </>
      ),
    },
  }[story.status]

  return (
    <div role="status" className="mb-5 flex gap-3 rounded-xl2 border border-gold/40 bg-gold-light/60 p-4 text-sm text-ink2">
      <span className="mt-0.5 text-gold">{content.icon}</span>
      <div>
        <div className="font-semibold text-ink">{content.title}</div>
        <div className="mt-0.5">{content.body}</div>
      </div>
    </div>
  )
}
