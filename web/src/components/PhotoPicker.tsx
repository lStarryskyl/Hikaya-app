import { t, useLocale, message } from '../i18n'
import { useRef, useState, type DragEvent } from 'react'
import { ArrowDown, ArrowUp, ImagePlus, X } from 'lucide-react'
import { ApiError } from '../api'
import { getPlaces } from '../discover'
import {
  addPhoto,
  deletePhoto,
  getLimits,
  pickGalleryPhoto,
  reorderPhotos,
  type StoryPhoto,
} from '../stories'
import { useApi } from '../useApi'
import Photo from './Photo'
import { PillButton } from './ui'

/**
 * Create Story's photo step: upload photos or pick them from a place gallery, put them in
 * order (the first is the cover), and remove any. Every change is saved to the draft at once.
 */
export default function PhotoPicker({
  storyId,
  photos,
  onChange,
  placeHint,
}: {
  storyId: string
  photos: StoryPhoto[]
  onChange: (photos: StoryPhoto[]) => void
  /** Opens the gallery on this place when it matches one. */
  placeHint?: string
}) {
  useLocale()

  const places = useApi(getPlaces, [])
  const limits = useApi(getLimits, [])
  const [gallerySlug, setGallerySlug] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  // The latest list, so a change that finishes later never builds on an older copy.
  const latest = useRef(photos)
  latest.current = photos
  const maxCount = limits.data?.photos_per_story ?? 12
  const full = photos.length >= maxCount
  const blocked = busy || full || !limits.data

  function commit(next: StoryPhoto[]) {
    latest.current = next
    onChange(next)
  }

  const galleryPlace =
    places.data?.find((p) => p.slug === gallerySlug) ??
    places.data?.find((p) => p.name === placeHint) ??
    places.data?.[0]

  async function run(action: () => Promise<StoryPhoto[]>) {
    setBusy(true)
    setError('')
    try {
      commit(await action())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('That did not work. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  function upload(files: FileList | null) {
    if (!files?.length || blocked || !limits.data) return
    const { photo_types, photo_max_mb } = limits.data
    // Check in the browser first, so a wrong or oversized file is never sent at all.
    const bad = Array.from(files).find(
      (f) => !photo_types.includes(f.type) || f.size > photo_max_mb * 1024 * 1024,
    )
    if (bad) {
      setError(
        photo_types.includes(bad.type)
          ? message('{name} is larger than {limit} MB.', { name: bad.name, limit: photo_max_mb })
          : message('{name} is not a PNG, JPEG or WebP photo.', { name: bad.name }),
      )
      return
    }
    void run(async () => {
      for (const file of Array.from(files)) {
        if (latest.current.length >= maxCount) break
        commit([...latest.current, await addPhoto(storyId, file)])
      }
      return latest.current
    })
  }

  function move(index: number, by: -1 | 1) {
    const ids = latest.current.map((p) => p.id)
    ;[ids[index], ids[index + by]] = [ids[index + by], ids[index]]
    void run(() => reorderPhotos(storyId, ids))
  }

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e: DragEvent) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault()
          setDragOver(false)
          upload(e.dataTransfer.files)
        }}
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 transition ${
          dragOver ? 'border-terracotta bg-terracotta-light/40' : 'border-border bg-cream/60'
        }`}
      >
        <ImagePlus size={28} className="mb-2 text-terracotta" />
        <p className="mb-1 text-sm text-ink2">{t('Drag and drop your photos here')}</p>
        <p className="mb-3 text-[11px] text-muted">
          {limits.data
            ? message('PNG, JPEG or WebP · up to {limit} MB each · up to {count} photos', {
                limit: limits.data.photo_max_mb,
                count: maxCount,
              })
            : limits.error || 'Loading the limits…'}
        </p>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          className="hidden"
          aria-label={t('Upload photos')}
          onChange={(e) => {
            upload(e.target.files)
            e.target.value = ''
          }}
        />
        <PillButton
          type="button"
          className="!py-2 text-xs disabled:opacity-50"
          disabled={blocked}
          onClick={() => input.current?.click()}
        >
          {busy ? t('Saving…') : t('Choose photos')}
        </PillButton>
      </div>

      {places.data && places.data.length > 0 && (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold">
              {t('No photos of your own? Pick from a gallery')}
            </div>
            <label className="text-[11px] text-muted2">
              <span className="sr-only">{t('Gallery')}</span>
              <select
                value={galleryPlace?.slug ?? ''}
                onChange={(e) => setGallerySlug(e.target.value)}
                className="rounded-lg border border-border bg-cream px-2 py-1 text-xs"
              >
                {places.data.map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
            {galleryPlace?.photos.map((p) => {
              const chosen = photos.some((s) => s.source === 'gallery' && s.photo.slug === p.slug)
              return (
                <button
                  key={p.slug}
                  type="button"
                  disabled={blocked || chosen}
                  onClick={() =>
                    void run(async () => [
                      ...latest.current,
                      await pickGalleryPhoto(storyId, p.slug),
                    ])
                  }
                  aria-label={
                    chosen
                      ? message('{caption} (added)', { caption: p.caption })
                      : message('Add {caption}', { caption: p.caption })
                  }
                  className="relative shrink-0 overflow-hidden rounded-lg border border-border disabled:opacity-50"
                >
                  <Photo photo={p} width={192} className="h-20 w-28 object-cover" />
                  {chosen && (
                    <span className="absolute inset-x-0 bottom-0 bg-black/60 py-0.5 text-[9px] text-cream">
                      {t('Added')}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {photos.length > 0 && (
        <ol
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          aria-label={t('Your photos, in order')}
        >
          {photos.map((p, i) => (
            <li key={p.id} className="relative overflow-hidden rounded-lg border border-border">
              <Photo
                photo={p.photo}
                width={240}
                alt={p.photo.caption || message('Photo {index}', { index: i + 1 })}
                className="aspect-square w-full object-cover"
              />
              {i === 0 && (
                <span className="absolute start-1.5 top-1.5 rounded bg-terracotta px-1.5 py-0.5 text-[9px] font-semibold text-cream">
                  {t('Cover')}
                </span>
              )}
              <div className="absolute end-1.5 top-1.5 flex gap-1">
                <button
                  type="button"
                  disabled={busy || i === 0}
                  onClick={() => move(i, -1)}
                  aria-label={message('Move photo {index} earlier', { index: i + 1 })}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white disabled:opacity-30"
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  disabled={busy || i === photos.length - 1}
                  onClick={() => move(i, 1)}
                  aria-label={message('Move photo {index} later', { index: i + 1 })}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white disabled:opacity-30"
                >
                  <ArrowDown size={13} />
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await deletePhoto(storyId, p.id)
                      return latest.current.filter((x) => x.id !== p.id)
                    })
                  }
                  aria-label={message('Remove photo {index}', { index: i + 1 })}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white"
                >
                  <X size={13} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
        >
          {t(error)}
        </p>
      )}
    </div>
  )
}
