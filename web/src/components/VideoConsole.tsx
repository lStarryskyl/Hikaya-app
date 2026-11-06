import { useEffect, useState } from 'react'
import { ApiError } from '../api'
import { getFeed } from '../discover'
import { message, t, useLocale } from '../i18n'
import { useApi } from '../useApi'
import {
  formatLength,
  generateVideo,
  getVideoConfig,
  getVideoJobs,
  planVideo,
  retryVideo,
  type NarratedPlan,
  type Soundtrack,
  type VideoMode,
  type VoiceSource,
} from '../videos'

type PlanState = { loading: boolean; data?: NarratedPlan; error?: string }

export default function VideoConsole() {
  useLocale()
  const configuration = useApi(getVideoConfig, [])
  const stories = useApi(() => getFeed({ limit: 100 }), [])
  const [revision, setRevision] = useState(0)
  const jobs = useApi(getVideoJobs, [revision])
  const [provider, setProvider] = useState('')
  const selectedProvider = provider || configuration.data?.default_provider || 'fake'
  const selected = configuration.data?.providers.find((item) => item.id === selectedProvider)
  const [model, setModel] = useState('')
  const [storyId, setStoryId] = useState('')
  const [prompt, setPrompt] = useState('A slow, respectful cinematic view of this heritage place.')
  const [aspect, setAspect] = useState<'16:9' | '9:16'>('16:9')
  const [seed, setSeed] = useState('42')
  const [mode, setMode] = useState<VideoMode>('clip')
  const [soundtrack, setSoundtrack] = useState<Soundtrack>('narration')
  const [subtitles, setSubtitles] = useState(true)
  // One switch for what is heard; the server setting NARRATED_VIDEO_AUDIO picks the default.
  const [voice, setVoice] = useState<VoiceSource | ''>('')
  const chosenVoice: VoiceSource = voice || configuration.data?.narrated_audio || 'soundtrack'
  const [plan, setPlan] = useState<PlanState>({ loading: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = jobs.data?.some((job) => job.status === 'queued' || job.status === 'running')
  // Narrated videos need a provider that makes shots of a chosen length.
  const canNarrate = selected?.max_shot_seconds != null
  const narrated = mode === 'narrated' && canNarrate
  const chosenModel = model || selected?.models[0] || ''
  const planReady = !narrated || (!plan.loading && !plan.error && plan.data !== undefined)
  useEffect(() => {
    if (!narrated || !storyId || !chosenModel) {
      setPlan({ loading: false })
      return
    }
    // Show the shots and the cost before anything is queued; a stale answer is ignored.
    let current = true
    setPlan({ loading: true })
    const timer = window.setTimeout(() => {
      planVideo({
        story_id: storyId,
        provider: selectedProvider,
        model: chosenModel,
        aspect_ratio: aspect,
        mode: 'narrated',
        soundtrack,
        audio: chosenVoice,
      }).then(
        (data) => {
          if (current) setPlan({ loading: false, data })
        },
        (e: unknown) => {
          if (current)
            setPlan({
              loading: false,
              error: e instanceof ApiError ? e.message : 'The video could not be planned.',
            })
        },
      )
    }, 300)
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [narrated, storyId, selectedProvider, chosenModel, soundtrack, aspect, chosenVoice])
  async function retry(id: string, confirmResubmit = false) {
    setError('')
    try {
      await retryVideo(id, confirmResubmit)
      setRevision((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('The video could not be retried.'))
    }
  }
  function resubmit(id: string, shot: number) {
    // The provider may already have accepted (and billed) the unconfirmed shot.
    if (
      window.confirm(
        message(
          'Submit shot {shot} again? If the provider already accepted it, it may be billed twice.',
          { shot },
        ),
      )
    )
      void retry(id, true)
  }
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setRevision((r) => r + 1), 1500)
    return () => window.clearInterval(timer)
  }, [pending])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !selected?.available || !configuration.data?.enabled || !planReady) return
    setError('')
    setBusy(true)
    try {
      await generateVideo({
        story_id: storyId,
        provider: selectedProvider,
        model: model || selected.models[0],
        prompt,
        aspect_ratio: aspect,
        seed: Number(seed),
        mode: narrated ? 'narrated' : 'clip',
        ...(narrated ? { soundtrack, subtitles, audio: chosenVoice } : {}),
      })
      setRevision((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Video generation could not start.'))
    } finally {
      setBusy(false)
    }
  }
  const field = 'mt-1 block w-full rounded-lg border border-border bg-panel p-2 text-sm'
  return (
    <section
      aria-labelledby="video-heading"
      className="rounded-xl2 border border-border bg-panel p-5"
    >
      <h2 id="video-heading" className="font-serif text-xl">
        {t('Staff AI video studio')}
      </h2>
      <p className="my-3 text-sm text-muted2">
        {t(
          'Generate a short preview from a story photo. Paid generation needs a configured provider, live AI, and room in the spending budget.',
        )}
      </p>
      {configuration.data && !configuration.data.enabled && (
        <p role="status" className="my-3 rounded-lg bg-gold-light p-3 text-sm text-gold">
          {t(
            'AI video generation is disabled. Set ENABLE_AI_VIDEO on the server to enable this console.',
          )}
        </p>
      )}
      {selected?.supports_seed === false && (
        <p className="mb-3 text-sm text-muted2">
          {selected?.supports_aspect === false
            ? t('This model follows the input photo framing and does not support seeds.')
            : t('This model does not support seeds.')}
        </p>
      )}
      <form onSubmit={(event) => void submit(event)} className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          {t('Story')}
          <select
            required
            value={storyId}
            onChange={(event) => setStoryId(event.target.value)}
            className={field}
          >
            <option value="">{t('Choose a story')}</option>
            {stories.data?.items.map((story) => (
              <option key={story.id} value={story.id}>
                {story.title}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {t('Video provider')}
          <select
            value={selectedProvider}
            onChange={(event) => {
              setProvider(event.target.value)
              setModel('')
            }}
            className={field}
          >
            {configuration.data?.providers.map((item) => (
              <option key={item.id} value={item.id}>
                {t(item.label)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {t('Model version')}
          <select
            value={model || selected?.models[0] || ''}
            onChange={(event) => setModel(event.target.value)}
            className={field}
          >
            {selected?.models.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {t('Video type')}
          <select
            value={narrated ? 'narrated' : 'clip'}
            onChange={(event) => setMode(event.target.value as VideoMode)}
            className={field}
          >
            <option value="clip">{t('Short clip (6 s)')}</option>
            <option value="narrated" disabled={!canNarrate}>
              {message('Narrated video (story soundtrack, up to {seconds} s)', {
                seconds: configuration.data?.narrated_max_seconds ?? 60,
              })}
            </option>
          </select>
        </label>
        {narrated ? (
          <label className="text-sm">
            {t('Soundtrack')}
            <select
              value={soundtrack}
              onChange={(event) => setSoundtrack(event.target.value as Soundtrack)}
              className={field}
            >
              <option value="narration">{t('Story narration')}</option>
              <option value="recording">{t("Storyteller's recording")}</option>
            </select>
          </label>
        ) : (
          selected &&
          !canNarrate && (
            <p className="self-end text-sm text-muted2">
              {t('Narrated videos need Gemini Omni Flash or the offline demo.')}
            </p>
          )
        )}
        {narrated && (
          <div className="text-sm sm:col-span-2">
            <span id="voice-label">{t('Voice')}</span>
            <div
              role="group"
              aria-labelledby="voice-label"
              className="mt-1 flex w-fit overflow-hidden rounded-full border border-border"
            >
              {(['soundtrack', 'omni'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={chosenVoice === value}
                  onClick={() => setVoice(value)}
                  className={`px-4 py-2 ${
                    chosenVoice === value ? 'bg-terracotta text-cream' : 'bg-panel text-ink'
                  }`}
                >
                  {t(value === 'omni' ? "Omni's own voice" : 'ElevenLabs narration')}
                </button>
              ))}
            </div>
            {chosenVoice === 'omni' && (
              <div className="mt-2 space-y-1 text-muted2">
                <p>
                  {t(
                    "Omni speaks the story's words itself, with the scene's natural sounds. Google evaluates Omni in English only, so the Arabic voice may vary; subtitles are approximate.",
                  )}
                </p>
                <p>
                  {t(
                    "In Omni's own voice, the soundtrack only sets the shot timing and subtitles.",
                  )}
                </p>
              </div>
            )}
          </div>
        )}
        {narrated && (
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              checked={subtitles}
              onChange={(event) => setSubtitles(event.target.checked)}
            />
            {t('Burn in subtitles')}
          </label>
        )}
        <label className="text-sm">
          {t('Aspect ratio')}
          <select
            value={aspect}
            disabled={selected?.supports_aspect === false}
            onChange={(event) => setAspect(event.target.value as '16:9' | '9:16')}
            className={field}
          >
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
          </select>
        </label>
        <label className="text-sm">
          {t('Seed')}
          <input
            type="number"
            disabled={selected?.supports_seed === false}
            min="0"
            max="2147483647"
            required
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
            className={field}
          />
        </label>
        <label className="text-sm sm:col-span-2">
          {t('Visual direction')}
          <textarea
            maxLength={1000}
            required
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            className={field}
          />
        </label>
        {selected && !selected.available && (
          <p role="status" className="text-sm text-terracotta-dark sm:col-span-2">
            {t(selected.reason)}
          </p>
        )}
        {narrated && storyId && (
          <p
            role="status"
            className={`text-sm sm:col-span-2 ${plan.error ? 'text-terracotta-dark' : 'text-muted2'}`}
          >
            {plan.loading
              ? t('Planning the video…')
              : plan.error
                ? t(plan.error)
                : plan.data &&
                  message(
                    'Shots: {shots} · Length: {length} · Lines covered: {lines} of {total} · Estimated cost about {usd} USD',
                    {
                      shots: plan.data.shots.length,
                      length: formatLength(plan.data.seconds),
                      lines: plan.data.lines,
                      total: plan.data.lines_total,
                      usd: plan.data.estimate_usd,
                    },
                  )}
          </p>
        )}
        {narrated && storyId && !plan.loading && plan.data?.script && (
          <p className="text-sm text-muted2 sm:col-span-2">
            {t(
              plan.data.script === 'gemini'
                ? 'Shot script: refined by Gemini for continuity'
                : 'Shot script: follows the story text (set SCRIPT_PROVIDER=gemini on the server to refine it)',
            )}
          </p>
        )}
        {narrated && storyId && !plan.loading && plan.data && !plan.data.english && (
          <p role="status" className="text-sm text-gold sm:col-span-2">
            {t(
              'This story has no English translation of every line: shot prompts use the spoken text and subtitles have one line.',
            )}
          </p>
        )}
        <button
          type="submit"
          disabled={
            busy || !storyId || !selected?.available || !configuration.data?.enabled || !planReady
          }
          className="w-fit rounded-full bg-terracotta px-4 py-2 text-cream disabled:opacity-50"
        >
          {t(
            busy
              ? 'Queuing preview…'
              : narrated
                ? 'Generate narrated video'
                : 'Generate video preview',
          )}
        </button>
      </form>
      {(error || configuration.error || stories.error || jobs.error) && (
        <p role="alert" className="mt-4 text-sm text-terracotta-dark">
          {t(error || configuration.error || stories.error || jobs.error)}
        </p>
      )}
      <div className="mt-5 space-y-4">
        {jobs.data?.map((job) => (
          <article key={job.id} className="rounded-lg border border-border p-4">
            <h3 className="font-medium">{job.model}</h3>
            {job.mode === 'narrated' && (
              <p className="text-sm text-muted2">
                {message('Narrated video · Shots: {shots} · Length: {length}', {
                  shots: job.shots ?? 0,
                  length: formatLength(job.seconds ?? 0),
                })}
                {job.audio && (
                  <>
                    {' · '}
                    {message('Voice: {voice}', {
                      voice: t(job.audio === 'omni' ? "Omni's own voice" : 'ElevenLabs narration'),
                    })}
                  </>
                )}
              </p>
            )}
            <p role="status" className="my-2 text-sm">
              {t(job.progress)} ·{' '}
              {job.mode === 'narrated' && job.shot != null && (
                <>
                  {message('Shot {shot} of {shots}', { shot: job.shot, shots: job.shots ?? 0 })}{' '}
                  ·{' '}
                </>
              )}
              {t(
                job.status === 'done'
                  ? 'Complete'
                  : job.status === 'failed'
                    ? 'Failed'
                    : 'Processing',
              )}
            </p>
            {(job.status === 'queued' || job.status === 'running') && (
              <progress aria-label={t('Video generation progress')} className="w-full" />
            )}
            {job.demo && (
              <p className="my-2 text-sm text-gold">
                {t(
                  'Offline demo preview: a saved provider sample is replayed. No AI request was sent.',
                )}
              </p>
            )}
            {job.error && (
              <p role="alert" className="text-sm text-terracotta-dark">
                {t(job.error)}
              </p>
            )}
            {job.status === 'failed' && job.needs_confirmation && (
              <div className="mt-2 space-y-2">
                <p className="text-sm text-gold">
                  {message(
                    'The provider never confirmed shot {shot}. Check your provider account first: submitting it again may be billed twice.',
                    { shot: job.shot ?? 0 },
                  )}
                </p>
                <button
                  type="button"
                  onClick={() => resubmit(job.id, job.shot ?? 0)}
                  className="w-fit rounded-full border border-terracotta px-3 py-1 text-sm text-terracotta-dark"
                >
                  {t('Submit the shot again')}
                </button>
              </div>
            )}
            {job.status === 'failed' && job.retryable && (
              <button
                type="button"
                onClick={() => void retry(job.id)}
                className="mt-2 w-fit rounded-full border border-terracotta px-3 py-1 text-sm text-terracotta-dark"
              >
                {t('Retry from the failed shot')}
              </button>
            )}
            {job.video_url && (
              <video
                controls
                muted
                playsInline
                preload="none"
                src={job.video_url}
                aria-label={t('Generated video preview')}
                className="mt-3 max-h-96 w-full rounded-lg bg-black"
              />
            )}
            {job.script && (
              <details className="mt-3 text-sm">
                <summary>{t('Shot script')}</summary>
                <dl className="mt-2 space-y-1">
                  <div>
                    <dt className="font-medium">{t('Cast')}</dt>
                    <dd dir="auto">{job.script.cast}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">{t('Setting')}</dt>
                    <dd dir="auto">{job.script.setting}</dd>
                  </div>
                  {job.audio === 'omni' && (
                    <div>
                      <dt className="font-medium">{t('Narrator')}</dt>
                      <dd dir="auto">{job.script.narrator}</dd>
                    </div>
                  )}
                </dl>
                <ol className="mt-2 list-decimal space-y-2 ps-5">
                  {job.script.shots.map((shot, index) => (
                    <li key={`${index}-${shot.action}`}>
                      <p dir="auto">{shot.action}</p>
                      <p dir="auto" className="text-muted2">
                        {message('Camera: {camera}', { camera: shot.camera })}
                      </p>
                      <p dir="auto" className="text-muted2">
                        {job.audio === 'omni'
                          ? message('Sound: {sound}', { sound: shot.sound })
                          : message('Sound (for later sound design): {sound}', {
                              sound: shot.sound,
                            })}
                      </p>
                    </li>
                  ))}
                </ol>
              </details>
            )}
            <details className="mt-3 text-sm">
              <summary>{t('Prompt sent to the provider')}</summary>
              <p dir="auto" className="mt-2 whitespace-pre-wrap">
                {job.prompt}
              </p>
            </details>
          </article>
        ))}
      </div>
    </section>
  )
}
