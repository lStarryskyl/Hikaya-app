import { useRef, useState, type DragEvent } from 'react'
import { ArrowDown, ArrowUp, ImagePlus, X } from 'lucide-react'
import { ApiError } from '../api'
import { getPlaces } from '../discover'
import {
  PHOTO_LIMITS, addPhoto, deletePhoto, pickGalleryPhoto, reorderPhotos, type StoryPhoto,
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
  const places = useApi(getPlaces, [])
  const [gallerySlug, setGallerySlug] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const full = photos.length >= PHOTO_LIMITS.maxCount

  const galleryPlace =
    places.data?.find((p) => p.slug === gallerySlug) ??
    places.data?.find((p) => p.name === placeHint) ??
    places.data?.[0]

  async function run(action: () => Promise<StoryPhoto[]>) {
    setBusy(true)
    setError('')
    try {
      onChange(await action())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function upload(files: FileList | null) {
    if (!files?.length) return
    void run(async () => {
      let next = photos
      for (const file of Array.from(files)) {
        if (next.length >= PHOTO_LIMITS.maxCount) break
        next = [...next, await addPhoto(storyId, file)]
        onChange(next)
      }
      return next
    })
  }

  function move(index: number, by: -1 | 1) {
    const ids = photos.map((p) => p.id)
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
        <p className="mb-1 text-sm text-ink2">Drag and drop your photos here</p>
        <p className="mb-3 text-[11px] text-muted">
          {PHOTO_LIMITS.types} · up to {PHOTO_LIMITS.maxMb} MB each · up to {PHOTO_LIMITS.maxCount} photos
        </p>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          className="hidden"
          aria-label="Upload photos"
          onChange={(e) => {
            upload(e.target.files)
            e.target.value = ''
          }}
        />
        <PillButton
          type="button"
          className="!py-2 text-xs disabled:opacity-50"
          disabled={busy || full}
          onClick={() => input.current?.click()}
        >
          {busy ? 'Saving…' : 'Choose photos'}
        </PillButton>
      </div>

      {places.data && places.data.length > 0 && (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold">No photos of your own? Pick from a gallery</div>
            <label className="text-[11px] text-muted2">
              <span className="sr-only">Gallery</span>
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
                  disabled={busy || full || chosen}
                  onClick={() => void run(async () => [...photos, await pickGalleryPhoto(storyId, p.slug)])}
                  aria-label={chosen ? `${p.caption} (added)` : `Add ${p.caption}`}
                  className="relative shrink-0 overflow-hidden rounded-lg border border-border disabled:opacity-50"
                >
                  <Photo photo={p} width={192} className="h-20 w-28 object-cover" />
                  {chosen && (
                    <span className="absolute inset-x-0 bottom-0 bg-black/60 py-0.5 text-[9px] text-cream">Added</span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {photos.length > 0 && (
        <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Your photos, in order">
          {photos.map((p, i) => (
            <li key={p.id} className="relative overflow-hidden rounded-lg border border-border">
              <Photo photo={p.photo} width={240} alt={p.photo.caption || `Photo ${i + 1}`} className="aspect-square w-full object-cover" />
              {i === 0 && (
                <span className="absolute left-1.5 top-1.5 rounded bg-terracotta px-1.5 py-0.5 text-[9px] font-semibold text-cream">
                  Cover
                </span>
              )}
              <div className="absolute right-1.5 top-1.5 flex gap-1">
                <button
                  type="button"
                  disabled={busy || i === 0}
                  onClick={() => move(i, -1)}
                  aria-label={`Move photo ${i + 1} earlier`}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white disabled:opacity-30"
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  disabled={busy || i === photos.length - 1}
                  onClick={() => move(i, 1)}
                  aria-label={`Move photo ${i + 1} later`}
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
                      return photos.filter((x) => x.id !== p.id)
                    })
                  }
                  aria-label={`Remove photo ${i + 1}`}
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
        <p role="alert" className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark">
          {error}
        </p>
      )}
    </div>
  )
}
