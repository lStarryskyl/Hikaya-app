import { t, useLocale, message } from '../i18n'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, Check, Cloud, Globe2, MapPin, Music } from 'lucide-react'
import { PillButton } from '../components/ui'
import JordanMap from '../components/JordanMap'
import PhotoPicker from '../components/PhotoPicker'
import Recorder, { recordingFormat } from '../components/Recorder'
import TranscriptEditor from '../components/TranscriptEditor'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { getPlaces } from '../discover'
import {
  CATEGORY_LABELS,
  LANGUAGE_LABELS,
  createStory,
  formatDuration,
  getConsent,
  getLimits,
  getStory,
  hasTranscript,
  submitStory,
  updateStory,
  uploadAudio,
  type CategoryValue,
  type LanguageValue,
  type NarrationSource,
  type StoryRecord,
} from '../stories'
import { useApi } from '../useApi'

const fieldClass =
  'mt-1 w-full rounded-lg border border-border bg-cream px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-terracotta/30'

function messageOf(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback
}

const steps = ['Record', 'Transcript', 'Photos', 'Publish']

type Pin = { lat: number; lng: number }

export default function CreateStoryPage() {
  useLocale()

  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<StoryRecord | null>(null)
  const [audioName, setAudioName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [audioError, setAudioError] = useState('')
  const [language, setLanguage] = useState<LanguageValue | ''>('')
  const [title, setTitle] = useState('')
  const [tags, setTags] = useState('')
  const [category, setCategory] = useState<CategoryValue | ''>('')
  const [narrationSource, setNarrationSource] = useState<NarrationSource>('polished')
  const [placeName, setPlaceName] = useState('')
  const [pin, setPin] = useState<Pin | null>(null)
  const [agreed, setAgreed] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState('')
  const audioInputRef = useRef<HTMLInputElement>(null)
  const places = useApi(getPlaces, [])
  const consent = useApi(getConsent, [])
  const limits = useApi(getLimits, [])
  const format = recordingFormat()
  const [params] = useSearchParams()
  const resumeId = params.get('story')
  const [resumeError, setResumeError] = useState('')
  const { user } = useAuth()

  // /create?story=<id> picks up a draft, or a story a reviewer sent back, where it was left.
  useEffect(() => {
    if (!resumeId || !user) return
    let cancelled = false
    getStory(resumeId)
      .then((story) => {
        if (cancelled) return
        // Only the author continues a story; staff and others see it on its own page.
        if (
          story.author.id !== user.id ||
          (story.status !== 'draft' && story.status !== 'needs_edit')
        ) {
          navigate(`/story/${story.id}`, { replace: true })
          return
        }
        setDraft(story)
        setLanguage(story.original_language ?? '')
        setTitle(story.title)
        setTags(story.tags.join(', '))
        setCategory(story.category ?? '')
        setNarrationSource(story.narration_source)
        setPlaceName(story.place_name)
        if (story.latitude !== null && story.longitude !== null)
          setPin({ lat: story.latitude, lng: story.longitude })
        if (story.audio) {
          setAudioName('Your recording')
          setStep(2)
        }
      })
      .catch((e) => !cancelled && setResumeError(messageOf(e, 'That story could not be opened.')))
    return () => {
      cancelled = true
    }
  }, [resumeId, navigate, user])

  const infoChips = [
    { icon: Music, label: 'Recording format', value: format?.label ?? t('Upload only') },
    { icon: Globe2, label: 'Languages', value: 'Jordanian · MSA · English' },
    { icon: Cloud, label: 'Saved as', value: 'A private draft' },
  ]

  /** The draft, created on first use, with the chosen language. */
  async function ensureDraft(): Promise<StoryRecord> {
    const fields = { original_language: language || null }
    if (!draft) return createStory(fields)
    if (draft.original_language === fields.original_language) return draft
    return updateStory(draft.id, fields)
  }

  async function sendAudio(file: File) {
    setAudioError('')
    setUploading(true)
    try {
      const story = await ensureDraft()
      setDraft(await uploadAudio(story.id, file, file.name))
      setAudioName(file.name)
    } catch (err) {
      setAudioError(messageOf(err, 'The upload failed. Please try again.'))
    } finally {
      setUploading(false)
    }
  }

  function choosePlace(name: string) {
    setPlaceName(name)
    const known = places.data?.find((p) => p.name.toLowerCase() === name.trim().toLowerCase())
    // A known place drops a pin there to start from; a click on the map refines it.
    if (known && !pin) setPin({ lat: known.latitude, lng: known.longitude })
  }

  async function publish() {
    if (!draft || !consent.data) return
    setPublishError('')
    setPublishing(true)
    try {
      await updateStory(draft.id, {
        title,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        category: category || null,
        place_name: placeName.trim(),
        latitude: pin?.lat ?? null,
        longitude: pin?.lng ?? null,
        narration_source: narrationSource,
      })
      const published = await submitStory(draft.id, consent.data.version)
      navigate(`/story/${published.id}`)
    } catch (err) {
      setPublishError(messageOf(err, 'Publishing failed. Please try again.'))
      setPublishing(false)
    }
  }

  // Asked in the photo step (so the gallery opens on it) and again before publishing.
  function placeField() {
    return (
      <label className="block text-xs font-medium text-muted2">
        {t('Place')}
        <input
          required
          maxLength={120}
          list="hikaya-places"
          value={placeName}
          onChange={(e) => choosePlace(e.target.value)}
          placeholder={t('A town, village or site')}
          className={fieldClass}
        />
        <datalist id="hikaya-places">
          {(places.data ?? []).map((p) => (
            <option key={p.slug} value={p.name} />
          ))}
        </datalist>
      </label>
    )
  }

  // Until a resumed story has loaded, nothing can be typed that its arrival would overwrite.
  if (resumeId && draft?.id !== resumeId && !resumeError) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-14 text-center text-sm text-muted2" role="status">
        {t('Opening your story…')}
      </div>
    )
  }

  const canContinue =
    (step === 1 && !!draft?.audio) || (step === 2 && hasTranscript(draft)) || step === 3

  return (
    <div className="mx-auto max-w-3xl px-6 py-14 text-center">
      <div className="mb-3 flex items-center justify-center gap-3 text-[11px] uppercase tracking-wider text-terracotta">
        <span className="h-px w-6 bg-terracotta" /> {t('Contribution portal')}{' '}
        <span className="h-px w-6 bg-terracotta" />
      </div>
      <h1 className="mb-2 font-serif text-3xl">{t('Craft your legacy')}</h1>
      <p className="mb-10 text-sm italic text-muted2">
        {t('"Every voice is a thread in the tapestry of our collective memory."')}
      </p>

      <div className="mb-10 flex items-center justify-center">
        {steps.map((label, i) => {
          const n = i + 1
          const state = n < step ? 'done' : n === step ? 'current' : 'todo'
          return (
            <div key={t(label)} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold ${
                    state === 'done'
                      ? 'bg-teal text-cream'
                      : state === 'current'
                        ? 'bg-terracotta text-cream'
                        : 'bg-border text-muted'
                  }`}
                >
                  {state === 'done' ? <Check size={14} /> : n}
                </div>
                <div
                  className={`mt-1.5 text-[11px] ${
                    state === 'current'
                      ? 'font-semibold text-terracotta'
                      : state === 'done'
                        ? 'text-teal'
                        : 'text-muted'
                  }`}
                >
                  {t(label)}
                </div>
              </div>
              {i < steps.length - 1 && (
                <div className={`mx-2 mb-5 h-0.5 w-16 ${n < step ? 'bg-teal' : 'bg-border'}`} />
              )}
            </div>
          )
        })}
      </div>

      {resumeError && (
        <p
          role="alert"
          className="mb-6 rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
        >
          {t(resumeError)}
        </p>
      )}
      {draft?.status === 'needs_edit' && draft.review?.note && (
        <div
          role="status"
          className="mb-6 rounded-xl2 border border-gold/40 bg-gold-light/60 p-4 text-start text-sm text-ink2"
        >
          <div className="font-semibold text-ink">{t('The reviewer asked for changes')}</div>
          <q className="mt-1 block italic">{draft.review.note}</q>
        </div>
      )}

      {step === 1 && (
        <div className="text-start">
          <h2 className="mb-1 text-center font-serif text-xl">{t('Speak your story')}</h2>
          <p className="mb-6 text-center text-sm text-muted">
            {t('Your voice carries the weight of history. Find a quiet space and start sharing.')}
          </p>

          <label className="mx-auto mb-5 block max-w-xs text-start text-xs font-medium text-muted2">
            {t('Language you speak in the recording')}
            <select
              value={language}
              onChange={async (e) => {
                const value = e.target.value as LanguageValue
                setLanguage(value)
                // Changing it after upload re-runs transcription in the right language.
                if (draft) {
                  try {
                    setDraft(await updateStory(draft.id, { original_language: value }))
                  } catch (err) {
                    setAudioError(messageOf(err, 'Could not change the language.'))
                  }
                }
              }}
              className={fieldClass}
            >
              <option value="" disabled>
                {t('Choose a language')}
              </option>
              {Object.entries(LANGUAGE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>

          <Recorder onRecorded={(file) => void sendAudio(file)} disabled={!language || uploading} />
          {!language && (
            <p className="mt-2 text-center text-[11px] text-muted">
              {t('Choose the language first, then record or upload.')}
            </p>
          )}

          <div className="mt-4 rounded-xl2 border border-border bg-panel p-5 text-center">
            <input
              ref={audioInputRef}
              type="file"
              accept="audio/*,video/webm"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void sendAudio(file)
              }}
              aria-label={t('Upload an audio recording')}
            />
            <p className="mb-3 text-sm text-ink2">{t('Or upload a recording you already have')}</p>
            <PillButton
              type="button"
              variant="outline"
              disabled={uploading || !language}
              onClick={() => audioInputRef.current?.click()}
              className="disabled:opacity-60"
            >
              <Cloud size={14} />{' '}
              {uploading
                ? t('Uploading…')
                : draft?.audio
                  ? t('Replace audio file')
                  : t('Upload audio file')}
            </PillButton>
            <p className="mt-2 text-[11px] text-muted">
              {t('WebM, Ogg, MP3, M4A or WAV')}
              {limits.data &&
                message(' · up to {size} MB · up to {minutes} minutes', {
                  size: limits.data.audio_max_mb,
                  minutes: limits.data.audio_max_minutes,
                })}
            </p>
            {draft?.audio && (
              <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-teal-light px-3 py-1 text-xs font-medium text-teal">
                <Check size={12} /> {audioName} · {formatDuration(draft.duration_ms)}
              </p>
            )}
            {audioError && (
              <p
                role="alert"
                className="mt-3 rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
              >
                {t(audioError)}
              </p>
            )}
          </div>

          <div className="my-6 grid grid-cols-3 gap-3">
            {infoChips.map(({ icon: Icon, label, value }) => (
              <div key={t(label)} className="rounded-xl border border-border px-3 py-4 text-center">
                <Icon size={16} className="mx-auto mb-2 text-terracotta" />
                <div className="text-[10px] uppercase tracking-wide text-muted">{t(label)}</div>
                <div className="mt-0.5 text-xs font-semibold">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {step === 2 && draft && <TranscriptEditor storyId={draft.id} onStory={setDraft} />}

      {step === 3 && draft && (
        <div className="space-y-4 text-start">
          <div className="rounded-xl2 border border-border bg-panel p-6">
            <div className="mb-4 max-w-xs">{placeField()}</div>
            <h3 className="font-serif text-lg">{t('Add photos')}</h3>
            <p className="mb-4 text-xs text-muted">
              {t(
                "They become your story's slideshow. The first photo is the cover. Photos are optional.",
              )}
            </p>
            <PhotoPicker
              storyId={draft.id}
              photos={draft.photos}
              placeHint={placeName}
              onChange={(photos) => setDraft((d) => (d ? { ...d, photos } : d))}
            />
          </div>
        </div>
      )}

      {step === 4 && draft && (
        <div className="grid gap-5 text-start md:grid-cols-2">
          <div className="rounded-xl2 border border-border bg-panel p-5">
            <div className="mb-3 flex items-center gap-1.5 text-xs text-muted">
              <MapPin size={13} /> {t('Click the map where the story happened')}
            </div>
            <div className="relative h-56 overflow-hidden rounded-lg">
              <JordanMap
                pins={
                  pin
                    ? [
                        {
                          id: 'draft',
                          storyId: 'draft',
                          lat: pin.lat,
                          lng: pin.lng,
                          kind: 'recent',
                          label: title || 'Your story',
                        },
                      ]
                    : []
                }
                focusedStoryId={pin ? 'draft' : null}
                zoom={6.3}
                flyToFocused
                showNavControl
                onMapClick={(lng, lat) =>
                  setPin({ lat: Number(lat.toFixed(5)), lng: Number(lng.toFixed(5)) })
                }
                className="absolute inset-0"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted2" aria-live="polite">
              {pin
                ? message('Pinned at {lat}, {lng}', {
                    lat: pin.lat.toFixed(4),
                    lng: pin.lng.toFixed(4),
                  })
                : t('No pin yet.')}
            </p>
          </div>
          <form
            className="space-y-3 rounded-xl2 border border-border bg-panel p-5"
            onSubmit={(e) => {
              e.preventDefault()
              void publish()
            }}
          >
            <label className="block text-xs font-medium text-muted2">
              {t('Title')}
              <input
                required
                maxLength={120}
                value={t(title)}
                onChange={(e) => setTitle(e.target.value)}
                className={fieldClass}
              />
            </label>
            <label className="block text-xs font-medium text-muted2">
              {t('Category')}
              <select
                required
                value={category}
                onChange={(e) => setCategory(e.target.value as CategoryValue)}
                className={fieldClass}
              >
                <option value="" disabled>
                  {t('Choose a category')}
                </option>
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            {placeField()}
            {draft.original_language && draft.original_language !== 'msa' && (
              <label className="block text-xs font-medium text-muted2">
                {t('The narration reads')}
                <select
                  value={narrationSource}
                  onChange={(e) => setNarrationSource(e.target.value as NarrationSource)}
                  className={fieldClass}
                >
                  <option value="polished">
                    {t('Your polished words (')}
                    {t(LANGUAGE_LABELS[draft.original_language])})
                  </option>
                  <option value="msa">{t('The Modern Standard Arabic translation')}</option>
                </select>
                <span className="mt-1 block text-[11px] font-normal text-muted">
                  {t(
                    'A voice reads your story aloud once it is published; listeners can switch between it and your recording.',
                  )}
                </span>
              </label>
            )}
            <label className="block text-start text-sm">
              {t('Tags (comma-separated, up to 10)')}
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                maxLength={410}
                className={fieldClass}
                placeholder={t('weaving, heritage')}
              />
            </label>
            {consent.data && (
              <label className="flex items-start gap-2 rounded-lg bg-cream p-3 text-xs leading-relaxed text-ink2">
                <input
                  type="checkbox"
                  required
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  className="mt-0.5 accent-terracotta"
                />
                <span>{consent.data.text}</span>
              </label>
            )}
            {consent.error && (
              <p
                role="alert"
                className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
              >
                {t(
                  'The rights statement could not be loaded, so publishing is not possible yet. Reload the page to try again.',
                )}
              </p>
            )}
            {publishError && (
              <p
                role="alert"
                className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
              >
                {t(publishError)}
              </p>
            )}
            <PillButton
              type="submit"
              variant="teal"
              disabled={publishing || !agreed || !pin || !consent.data}
              className="disabled:opacity-60"
            >
              <Check size={14} />{' '}
              {publishing
                ? t('Publishing…')
                : draft?.status === 'needs_edit'
                  ? t('Resubmit story')
                  : t('Publish story')}
            </PillButton>
            {!pin && (
              <p className="text-[11px] text-muted">{t('Place a pin on the map to publish.')}</p>
            )}
          </form>
        </div>
      )}

      {step < 4 && (
        <div className="mt-6 flex justify-center gap-3">
          {step > 1 && (
            <PillButton variant="outline" onClick={() => setStep(step - 1)}>
              {t('Back')}
            </PillButton>
          )}
          <PillButton
            variant="primary"
            onClick={() => setStep(step + 1)}
            disabled={!canContinue}
            className="disabled:cursor-not-allowed disabled:opacity-50"
          >
            {step === 3 && !draft?.photos.length ? t('Skip photos') : t('Continue')}{' '}
            <ArrowRight className="rtl:rotate-180" size={14} />
          </PillButton>
        </div>
      )}

      <div className="mt-16 grid gap-8 border-t border-border pt-8 text-start md:grid-cols-3">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">
            {t('Recording tips')}
          </div>
          <p className="text-[13px] leading-relaxed text-muted2">
            {t(
              'Seek a room with soft fabrics to reduce echo. Speak naturally, as if you are recounting the tale to a dear friend over tea.',
            )}
          </p>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">
            {t('Privacy & rights')}
          </div>
          <p className="text-[13px] leading-relaxed text-muted2">
            {t(
              'Your story stays a private draft until you publish it. Publishing needs your agreement to the rights statement shown in the last step.',
            )}
          </p>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">
            {t('Community guardrails')}
          </div>
          <p className="text-[13px] leading-relaxed text-muted2">
            {t(
              'We celebrate diversity and historical accuracy. Stories must respect regional traditions and avoid inflammatory or harmful content.',
            )}
          </p>
        </div>
      </div>

      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5 text-[11px] text-muted">
        <div>
          {t('HIKAYA ARCHIVE PROJECT ©')} {new Date().getFullYear()}
        </div>
      </footer>
    </div>
  )
}
