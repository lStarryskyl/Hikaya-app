import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, Check, Clock, Loader2, RotateCcw } from 'lucide-react'
import { ApiError } from '../api'
import { PillButton } from './ui'
import {
  LAYER_LABELS, MAX_SEGMENT_CHARS, MEDIA_STEPS, STEP_LABELS, editLayer, getPipeline, getStory, retryStep,
  textDirection, textFont, timestamp,
  type LayerKind, type PipelineStatus, type StoryRecord,
} from '../stories'

const POLL_MS = 1500

/** Create Story, step 2: real pipeline progress, and every text layer editable line by line. */
export default function TranscriptEditor({
  storyId,
  onStory,
}: {
  storyId: string
  onStory: (story: StoryRecord) => void
}) {
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null)
  const [story, setStory] = useState<StoryRecord | null>(null)
  const [active, setActive] = useState<LayerKind>('verbatim')
  const [drafts, setDrafts] = useState<Record<string, string[]>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const lastSignature = useRef('')
  // Every request takes a number; a response that is no longer the newest is ignored, so a
  // slow poll can never overwrite text saved after it started.
  const requestSeq = useRef(0)
  const mounted = useRef(true)
  useEffect(() => {
    // Set on every mount: React's strict mode mounts, unmounts and mounts again in development.
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  // Bumped after a save or retry, so polling starts again while new steps run.
  const [pollKey, setPollKey] = useState(0)

  const isLatest = (seq: number) => mounted.current && seq === requestSeq.current

  const refresh = useCallback(async () => {
    const seq = ++requestSeq.current
    const status = await getPipeline(storyId)
    if (!isLatest(seq)) return status
    setPipeline(status)
    // Fetch the story only when a step changed, so text appears as soon as it is ready.
    const signature = status.steps.map((s) => `${s.step}:${s.status}`).join('|')
    if (signature !== lastSignature.current) {
      const fresh = await getStory(storyId)
      if (!isLatest(seq)) return status
      lastSignature.current = signature
      setStory(fresh)
      onStory(fresh)
    }
    return status
  }, [storyId, onStory])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    async function tick() {
      try {
        const status = await refresh()
        const busy = status.steps.some((s) => s.status === 'queued' || s.status === 'running')
        if (!stopped && (busy || status.steps.length === 0)) timer = window.setTimeout(tick, POLL_MS)
      } catch (e) {
        if (!stopped) {
          setError(e instanceof ApiError ? e.message : 'Could not check progress.')
          timer = window.setTimeout(tick, POLL_MS * 2)
        }
      }
    }
    void tick()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [refresh, pollKey])

  const layers = story?.layers ?? []
  const layer = layers.find((l) => l.kind === active) ?? layers[0]
  // A draft only applies while it still has one text per line of the current version.
  const draft = layer ? drafts[layer.kind] : undefined
  const dirty = !!layer && !!draft && draft.length === layer.segments.length
  const texts = layer ? (dirty ? draft! : layer.segments.map((s) => s.text)) : []

  async function save() {
    if (!layer) return
    setSaving(true)
    setError('')
    const seq = ++requestSeq.current
    try {
      const fresh = await editLayer(storyId, layer.kind, texts)
      if (!mounted.current) return // the save started a newer request, so older polls are ignored
      setStory(fresh)
      onStory(fresh)
      setDrafts(({ [layer.kind]: _saved, ...rest }) => rest)
      lastSignature.current = ''
      setPollKey((k) => k + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Saving failed.')
    } finally {
      setSaving(false)
    }
  }

  async function retry(step: Parameters<typeof retryStep>[1]) {
    setError('')
    try {
      setPipeline(await retryStep(storyId, step))
      lastSignature.current = ''
      setPollKey((k) => k + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Retry failed.')
    }
  }

  return (
    <div className="grid gap-5 text-left md:grid-cols-[240px_1fr]">
      <div className="rounded-xl2 border border-border bg-panel p-5">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Progress</div>
        {!pipeline || pipeline.steps.length === 0 ? (
          <p className="text-sm text-muted2">Starting…</p>
        ) : (
          <ol className="space-y-3">
            {/* Narration and the slideshow run after submitting; the player shows them. */}
            {pipeline.steps.filter((s) => !MEDIA_STEPS.includes(s.step)).map((s) => (
              <li key={s.step} className="text-sm">
                <div className="flex items-center gap-2">
                  {s.status === 'done' ? (
                    <Check size={15} className="text-teal" aria-hidden />
                  ) : s.status === 'failed' ? (
                    <AlertCircle size={15} className="text-terracotta" aria-hidden />
                  ) : s.status === 'waiting' ? (
                    <Clock size={15} className="text-muted" aria-hidden />
                  ) : (
                    <Loader2
                      size={15}
                      className={`text-gold ${s.status === 'running' ? 'animate-spin' : ''}`}
                      aria-hidden
                    />
                  )}
                  <span className={s.status === 'done' ? 'text-ink2' : 'text-ink'}>{STEP_LABELS[s.step]}</span>
                </div>
                {s.status !== 'done' && <p className="ms-6 mt-0.5 text-[11px] text-muted2">{s.message}</p>}
                {s.status === 'failed' && (
                  <button
                    type="button"
                    onClick={() => void retry(s.step)}
                    className="ms-6 mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-terracotta hover:underline"
                  >
                    <RotateCcw size={11} /> Try again
                  </button>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="rounded-xl2 border border-border bg-panel p-5">
        {layers.length === 0 ? (
          <p className="text-sm text-muted2">Your transcript appears here as soon as it is ready.</p>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Text versions">
              {layers.map((l) => (
                <button
                  key={l.kind}
                  role="tab"
                  type="button"
                  aria-selected={l.kind === layer?.kind}
                  onClick={() => setActive(l.kind)}
                  className={`rounded-full px-3 py-1.5 text-[11px] font-semibold ${
                    l.kind === layer?.kind ? 'bg-terracotta text-cream' : 'bg-cream text-muted2 hover:bg-border'
                  }`}
                >
                  {LAYER_LABELS[l.kind]}
                  {drafts[l.kind] ? ' •' : ''}
                </button>
              ))}
            </div>
            {layer && (
              <div className="space-y-2">
                {layer.segments.map((seg, i) => (
                  <label key={seg.start_ms} className="flex items-start gap-3">
                    <span className="mt-2 w-10 shrink-0 font-mono text-[10px] text-terracotta">
                      {timestamp(seg.start_ms)}
                    </span>
                    <textarea
                      {...textDirection(layer.language)}
                      value={texts[i]}
                      rows={2}
                      maxLength={MAX_SEGMENT_CHARS}
                      aria-label={`${LAYER_LABELS[layer.kind]}, line ${i + 1}`}
                      onChange={(e) => {
                        const next = [...texts]
                        next[i] = e.target.value
                        setDrafts((d) => ({ ...d, [layer.kind]: next }))
                      }}
                      className={`w-full resize-y rounded-lg border border-border bg-cream px-3 py-2 text-sm leading-relaxed text-ink outline-none focus:ring-2 focus:ring-terracotta/30 ${textFont(layer.language)}`}
                    />
                  </label>
                ))}
                <div className="flex items-center justify-between pt-2">
                  <p className="text-[11px] text-muted">
                    {layer.kind === 'verbatim'
                      ? 'Saving the original words remakes the polished text and translations, replacing edits made to them.'
                      : layer.kind === 'polished'
                        ? 'Saving the polished text remakes the translations, replacing edits made to them.'
                        : 'Your edits to a translation are kept, unless an earlier version changes.'}
                  </p>
                  <PillButton
                    type="button"
                    variant="teal"
                    disabled={!dirty || saving}
                    onClick={() => void save()}
                    className="!py-2 text-xs disabled:opacity-50"
                  >
                    {saving ? 'Saving…' : 'Save changes'}
                  </PillButton>
                </div>
              </div>
            )}
          </>
        )}
        {error && (
          <p role="alert" className="mt-3 rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
