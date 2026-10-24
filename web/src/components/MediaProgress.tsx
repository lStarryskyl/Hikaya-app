import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { isStaff } from '../staff'
import { MEDIA_STEPS, STEP_LABELS, getPipeline, getStory, retryStep, type PipelineStep, type StoryRecord } from '../stories'
import { PillButton } from './ui'

const POLL_MS = 3000

/**
 * For the author and staff: the narration and slideshow while they are being made, with a
 * retry when one fails. Shows nothing to anyone else, or once both are done.
 */
export default function MediaProgress({
  story,
  onChange,
}: {
  story: StoryRecord
  onChange: (story: StoryRecord) => void
}) {
  const [steps, setSteps] = useState<PipelineStep[]>([])
  const [retrying, setRetrying] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [round, setRound] = useState(0)
  // Steps seen unfinished; when one of them is done, the story has a new file to show.
  const unfinished = useRef(new Set<string>())
  const { user } = useAuth()
  // Only the author and staff can see a story's progress; nobody else asks for it.
  const allowed = !!user && (user.id === story.author.id || isStaff(user.role))

  // Look every few seconds while a step is still running; each look waits for the last.
  useEffect(() => {
    if (!allowed) return
    let stopped = false
    let timer: number | undefined
    async function look() {
      let media: PipelineStep[]
      try {
        media = (await getPipeline(story.id)).steps.filter((s) => MEDIA_STEPS.includes(s.step))
      } catch {
        return // not the author or staff (404), or offline: show nothing
      }
      if (stopped) return
      setSteps(media)
      const busy = media.some((s) => s.status === 'queued' || s.status === 'running')
      const finished = media.filter((s) => s.status === 'done' && unfinished.current.has(s.step))
      media.forEach((s) => s.status !== 'done' && unfinished.current.add(s.step))
      finished.forEach((s) => unfinished.current.delete(s.step))
      // Something finished that the page does not show yet: load the story again.
      const missing =
        finished.length > 0 ||
        media.some((s) => s.step === 'narrate' && s.status === 'done' && !story.narration) ||
        media.some((s) => s.step === 'slideshow' && s.status === 'done' && !story.slideshow)
      if (missing) {
        try {
          const fresh = await getStory(story.id)
          if (!stopped) onChange(fresh)
        } catch {
          /* the next look tries again */
        }
      }
      if (!stopped && (busy || missing)) timer = window.setTimeout(look, POLL_MS)
    }
    void look()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [allowed, story.id, story.narration, story.slideshow, onChange, round])

  async function retry(step: PipelineStep['step']) {
    setRetrying(step)
    setError('')
    try {
      await retryStep(story.id, step)
      setRound((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work. Please try again.')
    } finally {
      setRetrying(null)
    }
  }

  const shown = steps.filter((s) => s.status !== 'done')
  if (!allowed || shown.length === 0) return null
  return (
    <div role="status" className="mb-4 space-y-2 rounded-xl2 border border-border bg-panel p-4 text-sm">
      {shown.map((s) => (
        <div key={s.step} className="flex flex-wrap items-center gap-2">
          {s.status === 'failed' ? (
            <AlertCircle size={15} className="text-terracotta" aria-hidden />
          ) : (
            <Loader2 size={15} className="animate-spin text-gold" aria-hidden />
          )}
          <span className="text-ink">{STEP_LABELS[s.step]}</span>
          <span className="text-[11px] text-muted2">{s.message}</span>
          {s.status === 'failed' && (
            <PillButton
              type="button"
              className="!py-1 text-xs"
              disabled={retrying !== null}
              onClick={() => void retry(s.step)}
            >
              {retrying === s.step ? 'Trying again…' : 'Try again'}
            </PillButton>
          )}
        </div>
      ))}
      {error && <p role="alert" className="text-[12px] text-terracotta-dark">{error}</p>}
    </div>
  )
}
