import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ImagePlus, X } from 'lucide-react'
import { ApiError } from '../api'
import { message, t, useLocale } from '../i18n'
import {
  getStory,
  staffAddPhoto,
  staffDeletePhoto,
  staffReorderPhotos,
  type StoryPhoto,
} from '../stories'
import Photo from './Photo'

/**
 * Staff: the photos on a submitted story's page, which visitors browse before its video
 * story. Staff can add, reorder and remove them after publishing; the first one also opens
 * a new narrated video.
 */
export default function StaffStoryPhotos({ storyId }: { storyId: string }) {
  useLocale()
  const [photos, setPhotos] = useState<StoryPhoto[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let live = true
    setPhotos(null)
    setError('')
    getStory(storyId)
      .then((story) => live && setPhotos(story.photos))
      .catch(
        (e) =>
          live &&
          setError(e instanceof ApiError ? e.message : 'That did not work. Please try again.'),
      )
    return () => {
      live = false
    }
  }, [storyId])

  const list = photos ?? []

  async function run(action: () => Promise<StoryPhoto[]>) {
    setBusy(true)
    setError('')
    try {
      setPhotos(await action())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function add(files: FileList | null) {
    if (!files?.length) return
    const chosen = Array.from(files)
    await run(async () => {
      let next = list
      for (const file of chosen) next = [...next, await staffAddPhoto(storyId, file)]
      return next
    })
    if (input.current) input.current.value = ''
  }

  function move(index: number, by: number) {
    const ids = list.map((p) => p.id)
    const [id] = ids.splice(index, 1)
    ids.splice(index + by, 0, id)
    void run(() => staffReorderPhotos(storyId, ids))
  }

  function remove(photoId: string) {
    void run(async () => {
      await staffDeletePhoto(storyId, photoId)
      return list.filter((p) => p.id !== photoId)
    })
  }

  return (
    <section
      aria-labelledby="staff-story-photos"
      className="mt-4 rounded-lg border border-border p-3"
    >
      <h3 id="staff-story-photos" className="text-sm font-medium">
        {t('Photos on the story page')}
      </h3>
      <p className="mb-2 text-xs text-muted2">
        {t('Visitors browse these before the video story. The first one opens a new video.')}
      </p>
      {list.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2">
          {list.map((p, i) => (
            <li key={p.id} className="w-28">
              <Photo
                photo={p.photo}
                width={288}
                alt={p.photo.caption || message('Photo {index}', { index: i + 1 })}
                className="h-20 w-28 rounded border border-border object-cover"
              />
              <div className="mt-1 flex items-center justify-between text-muted2">
                {i === 0 ? <span className="text-[11px] font-medium">{t('Cover')}</span> : <span />}
                <span className="flex gap-1">
                  <button
                    type="button"
                    disabled={busy || i === 0}
                    onClick={() => move(i, -1)}
                    aria-label={message('Move photo {index} earlier', { index: i + 1 })}
                    className="disabled:opacity-30"
                  >
                    <ArrowUp size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    disabled={busy || i === list.length - 1}
                    onClick={() => move(i, 1)}
                    aria-label={message('Move photo {index} later', { index: i + 1 })}
                    className="disabled:opacity-30"
                  >
                    <ArrowDown size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => remove(p.id)}
                    aria-label={message('Remove photo {index}', { index: i + 1 })}
                    className="disabled:opacity-30"
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <label className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-terracotta px-3 py-1 text-sm text-terracotta-dark">
        <ImagePlus size={14} aria-hidden="true" />
        {busy ? t('Saving…') : t('Choose photos')}
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          disabled={busy || photos === null}
          aria-label={t('Upload photos')}
          className="sr-only"
          onChange={(e) => void add(e.target.files)}
        />
      </label>
      {error && (
        <p role="alert" className="mt-2 text-sm text-terracotta-dark">
          {t(error)}
        </p>
      )}
    </section>
  )
}
