import { useState } from 'react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { t } from '../i18n'
import { isStaff } from '../staff'
import type { StoryRecord } from '../stories'
import { useApi } from '../useApi'
import { chooseNarrator, getVoices } from '../voices'

/**
 * Staff choose who narrates a story: the default voice or a consenting person's ready cloned
 * voice. The narration is made again (and its slideshow), which the progress card shows.
 */
export default function StaffNarrator({
  story,
  onQueued,
}: {
  story: StoryRecord
  onQueued: () => void
}) {
  const { user } = useAuth()
  const allowed =
    !!user &&
    isStaff(user.role) &&
    user.id !== story.author.id &&
    ['published', 'held', 'moderating'].includes(story.status)
  const voices = useApi(() => (allowed ? getVoices() : Promise.resolve([])), [allowed])
  // Starts on the story's current narrator, so saving it unchanged changes nothing.
  const [choice, setChoice] = useState(story.narrator_voice_id ?? '')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  if (!allowed) return null
  const ready = (voices.data ?? []).filter((voice) => voice.state === 'ready')
  return (
    <form
      className="mb-6 flex flex-wrap items-end gap-3 rounded-xl2 border border-border bg-panel p-4 text-sm"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setResult('')
        setError('')
        try {
          await chooseNarrator(story.id, choice || null)
          setResult(t('The narration is being made again.'))
          onQueued()
        } catch (err) {
          setError(
            err instanceof ApiError ? err.message : t('That did not work. Please try again.'),
          )
        } finally {
          setBusy(false)
        }
      }}
    >
      <label className="block min-w-56 flex-1 text-xs font-medium text-muted2">
        {t('Narrator voice (staff)')}
        <select
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          className="mt-1 w-full rounded-lg border border-border bg-cream p-2 text-sm text-ink"
        >
          <option value="">{t('Default voice')}</option>
          {ready.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voice.speaker_name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={busy}
        className="rounded-full border border-border px-4 py-2 text-xs font-medium text-ink2 hover:bg-cream disabled:opacity-50"
      >
        {t('Narrate again')}
      </button>
      {result && (
        <p role="status" className="basis-full text-xs text-teal">
          {result}
        </p>
      )}
      {error && (
        <p role="alert" className="basis-full text-xs text-terracotta-dark">
          {error}
        </p>
      )}
    </form>
  )
}
