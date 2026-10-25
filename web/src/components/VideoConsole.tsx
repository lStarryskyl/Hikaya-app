import { useEffect, useState } from 'react'
import { ApiError } from '../api'
import { getFeed } from '../discover'
import { t, useLocale } from '../i18n'
import { useApi } from '../useApi'
import { generateVideo, getVideoConfig, getVideoJobs } from '../videos'

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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = jobs.data?.some((job) => job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setRevision((r) => r + 1), 1500)
    return () => window.clearInterval(timer)
  }, [pending])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !selected?.available || !configuration.data?.enabled) return
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
          {t('This model follows the input photo framing and does not support seeds.')}
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
        <button
          type="submit"
          disabled={busy || !storyId || !selected?.available || !configuration.data?.enabled}
          className="w-fit rounded-full bg-terracotta px-4 py-2 text-cream disabled:opacity-50"
        >
          {t(busy ? 'Queuing preview…' : 'Generate video preview')}
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
            <p role="status" className="my-2 text-sm">
              {t(job.progress)} ·{' '}
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
