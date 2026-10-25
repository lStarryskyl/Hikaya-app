import { useEffect, useRef, useState } from 'react'
import Recorder from './Recorder'
import { ApiError } from '../api'
import { t, useLocale } from '../i18n'
import {
  cloneVoice,
  getVoiceConsent,
  getVoices,
  markVerified,
  revokeVoice,
  type VoiceClone,
} from '../voices'
import { useApi } from '../useApi'

export default function VoiceClonePanel() {
  const locale = useLocale()
  const consent = useApi(getVoiceConsent, [])
  const [revision, setRevision] = useState(0)
  const voices = useApi(getVoices, [revision])
  const [open, setOpen] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const [checks, setChecks] = useState([false, false, false])
  const [speaker, setSpeaker] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [duration, setDuration] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(crypto.randomUUID())
  const pending = voices.data?.some((voice) => voice.state === 'preparing')
  // Revoking deletes a person's voice everywhere, so it asks twice.
  const [confirming, setConfirming] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<string | null>(null)
  async function revoke(voice: VoiceClone) {
    if (confirming !== voice.id) {
      setConfirming(voice.id)
      return
    }
    setRevoking(voice.id)
    setError('')
    try {
      await revokeVoice(voice.id)
      setRevision((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('That did not work. Please try again.'))
    } finally {
      setRevoking(null)
      setConfirming(null)
    }
  }
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setRevision((r) => r + 1), 1500)
    return () => window.clearInterval(timer)
  }, [pending])
  useEffect(() => {
    if (!file) {
      setPreview('')
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    setDuration(0)
    return () => URL.revokeObjectURL(url)
  }, [file])
  useEffect(() => {
    if (open) dialog.current?.showModal()
    else dialog.current?.close()
  }, [open])
  function close() {
    if (busy) return
    setOpen(false)
    setFile(null)
    setChecks([false, false, false])
    setError('')
    requestId.current = crypto.randomUUID()
  }
  const agreed = checks.every(Boolean)
  async function submit() {
    if (!file || !consent.data || !agreed || busy) return
    setBusy(true)
    setError('')
    try {
      await cloneVoice(file, speaker.trim(), consent.data, locale, requestId.current)
      setOpen(false)
      setFile(null)
      setChecks([false, false, false])
      requestId.current = crypto.randomUUID()
      setRevision((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Voice cloning failed. Please try again.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      className="rounded-xl2 border border-border bg-panel p-5"
      aria-labelledby="voice-heading"
    >
      <h2 id="voice-heading" className="font-serif text-xl">
        {t('Voice cloning, with consent')}
      </h2>
      <p className="my-3 text-sm text-muted2">
        {t(
          'Staff only. The speaker must explicitly agree before recording or uploading a 30–60 second sample.',
        )}
      </p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={consent.loading || !!consent.error || consent.data?.available === false}
        className="rounded-full bg-terracotta px-4 py-2 text-cream disabled:opacity-50"
      >
        {t('Create a voice clone')}
      </button>
      {consent.data && !consent.data.available && consent.data.reason && (
        <p className="mt-2 text-sm text-terracotta-dark">{t(consent.data.reason)}</p>
      )}
      {(voices.error || consent.error) && <p role="alert">{voices.error || consent.error}</p>}
      {error && !open && (
        <p role="alert" className="mt-2 text-sm text-terracotta-dark">
          {error}
        </p>
      )}
      <ul className="mt-4 space-y-3">
        {voices.data?.map((voice) => (
          <li key={voice.id} className="rounded-lg bg-cream p-3 text-sm">
            <span dir="auto" className="font-semibold">
              {voice.speaker_name}
            </span>{' '}
            ·{' '}
            {t(
              voice.state === 'ready'
                ? voice.demo
                  ? 'Demo clone ready (no synthetic voice was created)'
                  : 'Voice ready'
                : voice.state === 'needs_verification'
                  ? 'Provider verification required'
                  : voice.state === 'failed'
                    ? 'Voice cloning failed'
                    : voice.state === 'revoked'
                      ? 'Revoked'
                      : 'Cloning in progress…',
            )}
            <p className="mt-1 text-xs text-muted2">
              {t('Consent saved')}: {new Date(voice.consent.at).toLocaleString(locale)}
            </p>
            {voice.message && (
              <p
                role={voice.state === 'failed' ? 'alert' : undefined}
                className="mt-2 text-terracotta-dark"
              >
                {t(voice.message)}
              </p>
            )}
            {voice.state === 'needs_verification' && (
              <button
                type="button"
                onClick={async () => {
                  setError('')
                  try {
                    await markVerified(voice.id)
                    setRevision((r) => r + 1)
                  } catch (e) {
                    setError(
                      e instanceof ApiError ? e.message : t('That did not work. Please try again.'),
                    )
                  }
                }}
                className="me-4 mt-2 text-xs font-semibold text-teal hover:underline"
              >
                {t('The speaker has verified it')}
              </button>
            )}
            {voice.state !== 'revoked' && (
              <button
                type="button"
                onClick={() => void revoke(voice)}
                disabled={revoking !== null}
                aria-label={`${t('Revoke voice')}: ${voice.speaker_name}`}
                className="mt-2 text-xs font-semibold text-terracotta-dark hover:underline disabled:opacity-50"
              >
                {revoking === voice.id
                  ? t('Revoking…')
                  : confirming === voice.id
                    ? t('Revoke and delete its sample and narrations? Click again')
                    : t('Revoke voice')}
              </button>
            )}
          </li>
        ))}
      </ul>
      <dialog
        ref={dialog}
        onCancel={(event) => {
          event.preventDefault()
          close()
        }}
        aria-labelledby="voice-consent-heading"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl2 bg-panel p-6 text-ink backdrop:bg-black/50"
      >
        <h2 id="voice-consent-heading" className="font-serif text-xl">
          {t('Voice consent')}
        </h2>
        <p className="my-4 text-sm leading-relaxed">
          {locale === 'ar' ? consent.data?.text_ar : consent.data?.text}
        </p>
        <label className="block text-sm">
          {t('Speaker name')}
          <input
            value={speaker}
            maxLength={80}
            onChange={(e) => setSpeaker(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-border p-2"
          />
        </label>
        <div className="my-4 space-y-3">
          {[
            'I am the speaker in this sample.',
            'I control the rights to this voice.',
            'I consent to storage, provider processing, and synthetic heritage narration.',
          ].map((label, i) => (
            <label key={label} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={checks[i]}
                disabled={busy}
                onChange={(e) =>
                  setChecks((previous) =>
                    previous.map((value, index) => (index === i ? e.target.checked : value)),
                  )
                }
              />
              {t(label)}
            </label>
          ))}
        </div>
        {open && agreed && (
          <div>
            <Recorder disabled={busy} maxSeconds={60} onRecorded={setFile} />
            <label className="my-3 block text-sm">
              {t('Or upload a voice sample')}
              <input
                type="file"
                accept="audio/*,video/webm"
                disabled={busy}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null)
                  e.target.value = ''
                }}
                className="mt-2 block w-full"
              />
            </label>
          </div>
        )}
        {preview && (
          <div className="my-3">
            {/* This private, untranscribed user sample has no text track yet; the story players have timed transcripts. */}
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <audio
              controls
              src={preview}
              aria-label={t('Voice sample playback')}
              onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
              onError={() => setError(t('This sample could not be played.'))}
            />
            <p className="mt-1 text-sm">
              {t('Record 30–60 seconds. The server checks the duration before creating a clone.')}
            </p>
          </div>
        )}
        {error && (
          <p role="alert" className="my-3 text-sm text-terracotta-dark">
            {t(error)}
          </p>
        )}
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => void submit()}
            disabled={
              !agreed ||
              !speaker.trim() ||
              !file ||
              (Number.isFinite(duration) && duration > 0 && (duration < 30 || duration > 60.5)) ||
              busy
            }
            className="rounded-full bg-terracotta px-4 py-2 text-cream disabled:opacity-50"
          >
            {t(busy ? 'Submitting…' : 'Consent and create clone')}
          </button>
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="rounded-full border border-border px-4 py-2"
          >
            {t('Cancel')}
          </button>
        </div>
      </dialog>
    </section>
  )
}
