import { t, useLocale } from '../i18n'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Clock, FilePen, Loader2 } from 'lucide-react'
import { ApiError } from '../api'
import { MODERATION_LABELS, getPipeline, getStory, retryStep, type StoryRecord } from '../stories'
import { PillButton } from './ui'

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
  useLocale()

  // Set when the check itself failed (the provider was down, say): polling stops until a retry.
  const [failure, setFailure] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [round, setRound] = useState(0)

  // While the check runs, look again every few seconds until the result is in. Each look
  // waits for the previous one, so slow answers never pile up.
  useEffect(() => {
    if (story.status !== 'moderating') return
    let stopped = false
    let timer: number | undefined
    async function look() {
      try {
        const fresh = await getStory(story.id)
        if (stopped) return
        if (fresh.status !== 'moderating') return onChange(fresh)
        const step = (await getPipeline(story.id)).steps.find((s) => s.step === 'moderate')
        if (stopped) return
        if (step?.status === 'failed') return setFailure(step.message)
      } catch {
        /* keep the current banner; the next look tries again */
      }
      if (!stopped) timer = window.setTimeout(look, POLL_MS)
    }
    timer = window.setTimeout(look, POLL_MS)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [story.id, story.status, onChange, round])

  async function retry() {
    setRetrying(true)
    try {
      await retryStep(story.id, 'moderate')
      setFailure('')
      setRound((r) => r + 1)
    } catch (e) {
      setFailure(e instanceof ApiError ? e.message : t('That did not work. Please try again.'))
    } finally {
      setRetrying(false)
    }
  }

  if (story.status === 'published') return null

  const raised = story.moderation?.labels.filter((l) => l.raised) ?? []
  const editLink = (label: string) => (
    <Link
      to={`/create?story=${story.id}`}
      className="font-semibold text-terracotta hover:underline"
    >
      {t(label)}
    </Link>
  )

  const content = {
    draft: {
      icon: <FilePen size={16} />,
      title: 'This story is a draft',
      body: (
        <>
          {t('Only you can see it.')}
          {editLink('Continue editing')}
        </>
      ),
    },
    moderating: failure
      ? {
          icon: <AlertTriangle size={16} />,
          title: 'The check could not finish',
          body: (
            <>
              <span role="alert">{failure}</span>
              <div className="mt-2">
                <PillButton
                  type="button"
                  className="!py-1.5 text-xs"
                  disabled={retrying}
                  onClick={() => void retry()}
                >
                  {retrying ? t('Trying again…') : t('Try again')}
                </PillButton>
              </div>
            </>
          ),
        }
      : {
          icon: <Loader2 size={16} className="animate-spin" />,
          title: 'We are checking your story',
          body: 'It will be published in a moment if nothing needs a closer look.',
        },
    held: {
      icon: <Clock size={16} />,
      title: 'Your story is under review',
      body: (
        <>
          {t('Our automatic check asked a reviewer to read it before it is published.')}
          {raised.length > 0 && (
            <ul className="mt-2 list-disc ps-5">
              {raised.map((l) => (
                <li key={l.label}>
                  <span className="font-medium">{t(MODERATION_LABELS[l.label])}</span>
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
          {story.review?.note ? (
            <q className="block italic">{story.review.note}</q>
          ) : (
            t('Please review your story.')
          )}
          <div className="mt-2">{editLink('Edit and resubmit')}</div>
        </>
      ),
    },
  }[story.status]

  return (
    <div
      role="status"
      className="mb-5 flex gap-3 rounded-xl2 border border-gold/40 bg-gold-light/60 p-4 text-sm text-ink2"
    >
      <span className="mt-0.5 text-gold">{content.icon}</span>
      <div>
        <div className="font-semibold text-ink">{content.title}</div>
        <div className="mt-0.5">{content.body}</div>
      </div>
    </div>
  )
}
