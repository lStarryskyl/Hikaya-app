import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  Cloud,
  Globe2,
  ImagePlus,
  Mic,
  Music,
  Trash2,
  Wand2,
  X,
} from 'lucide-react'
import { PillButton } from '../components/ui'
import JordanMap from '../components/JordanMap'
import { mapPins } from '../data/mock'

const steps = ['Record', 'Transcript', 'Visualize', 'Publish']

const infoChips = [
  { icon: Music, label: 'Audio fidelity', value: 'Lossless WAV' },
  { icon: Globe2, label: 'Auto-detect', value: 'Bilingual AI' },
  { icon: Cloud, label: 'Preservation', value: 'Cloud Sync' },
]

const waveHeights = [30, 55, 80, 45, 65, 95, 50, 70, 40, 85, 60, 35, 75, 55, 90]

type UploadedPhoto = { id: string; name: string; url: string }

export default function CreateStoryPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [animPct, setAnimPct] = useState(0)
  const [photos, setPhotos] = useState<UploadedPhoto[]>([])
  const [dragOver, setDragOver] = useState(false)
  const timerRef = useRef<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (recording) {
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [recording])

  useEffect(() => {
    if (step !== 3) return
    setAnimPct(0)
    const id = window.setInterval(() => {
      setAnimPct((p) => Math.min(100, p + 9))
    }, 260)
    return () => clearInterval(id)
  }, [step])

  useEffect(() => {
    return () => {
      photos.forEach((p) => URL.revokeObjectURL(p.url))
    }
    // only on unmount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')

  function addFiles(fileList: FileList | null) {
    if (!fileList) return
    const next: UploadedPhoto[] = []
    Array.from(fileList).forEach((file) => {
      if (!file.type.startsWith('image/')) return
      next.push({
        id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
        name: file.name,
        url: URL.createObjectURL(file),
      })
    })
    if (next.length) setPhotos((prev) => [...prev, ...next].slice(0, 8))
  }

  function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    addFiles(e.target.files)
    e.target.value = ''
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragOver(false)
    addFiles(e.dataTransfer.files)
  }

  function removePhoto(id: string) {
    setPhotos((prev) => {
      const target = prev.find((p) => p.id === id)
      if (target) URL.revokeObjectURL(target.url)
      return prev.filter((p) => p.id !== id)
    })
  }

  function next() {
    if (step < 4) setStep(step + 1)
    else {
      if (photos[0]) sessionStorage.setItem('hikaya-draft-cover', photos[0].url)
      navigate('/story/echoes-of-jerash')
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-14 text-center">
      <div className="mb-3 flex items-center justify-center gap-3 text-[11px] uppercase tracking-wider text-terracotta">
        <span className="h-px w-6 bg-terracotta" /> Contribution portal{' '}
        <span className="h-px w-6 bg-terracotta" />
      </div>
      <h1 className="mb-2 font-serif text-3xl">Craft your legacy</h1>
      <p className="mb-10 text-sm italic text-muted2">
        "Every voice is a thread in the tapestry of our collective memory."
      </p>

      <div className="mb-10 flex items-center justify-center">
        {steps.map((label, i) => {
          const n = i + 1
          const state = n < step ? 'done' : n === step ? 'current' : 'todo'
          return (
            <div key={label} className="flex items-center">
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
                  {label}
                </div>
              </div>
              {i < steps.length - 1 && (
                <div className={`mx-2 mb-5 h-0.5 w-16 ${n < step ? 'bg-teal' : 'bg-border'}`} />
              )}
            </div>
          )
        })}
      </div>

      {step === 1 && (
        <div className="text-left">
          <h2 className="mb-1 text-center font-serif text-xl">Speak your story</h2>
          <p className="mb-6 text-center text-sm text-muted">
            Your voice carries the weight of history. Find a quiet space and start sharing.
          </p>

          <div className="flex flex-col items-center rounded-xl2 border border-border bg-panel p-8">
            <div className="mb-6 flex h-16 items-end gap-1">
              {waveHeights.map((h, i) => (
                <span
                  key={i}
                  className="w-1.5 rounded-full bg-terracotta/70"
                  style={{ height: `${recording ? h : h * 0.4}%`, transition: 'height .3s ease' }}
                />
              ))}
            </div>
            <div className="mb-5 font-serif text-3xl">
              {mm}:{ss}
            </div>
            <button
              onClick={() => setRecording((r) => !r)}
              className={`flex h-16 w-16 items-center justify-center rounded-full text-cream transition ${
                recording ? 'bg-terracotta-dark' : 'bg-terracotta'
              }`}
            >
              <Mic size={22} />
            </button>
          </div>

          <div className="my-6 grid grid-cols-3 gap-3">
            {infoChips.map(({ icon: Icon, label, value }) => (
              <div key={label} className="rounded-xl border border-border px-3 py-4 text-center">
                <Icon size={16} className="mx-auto mb-2 text-terracotta" />
                <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
                <div className="mt-0.5 text-xs font-semibold">{value}</div>
              </div>
            ))}
          </div>

          <div className="text-center">
            <button
              onClick={next}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-ink2"
            >
              Done with recording? Continue to transcript <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="grid gap-5 text-left md:grid-cols-2">
          <div className="rounded-xl2 border border-border bg-panel p-5">
            <div className="mb-3 flex items-center gap-2 text-xs text-muted">
              <Globe2 size={14} /> Transcribed · Arabic detected
            </div>
            <div className="flex h-10 items-end gap-1">
              {waveHeights.slice(0, 10).map((h, i) => (
                <span key={i} className="w-1.5 rounded-full bg-gold/70" style={{ height: `${h}%` }} />
              ))}
            </div>
          </div>
          <div className="rounded-xl2 border border-border bg-panel p-5">
            <div className="mb-2 text-xs text-muted">Edit the transcript</div>
            <div
              contentEditable
              suppressContentEditableWarning
              className="min-h-[80px] text-sm leading-relaxed outline-none"
            >
              In old Salt, my grandfather kept a brass lantern by the stone stairway. Every dusk he
              would light it, and the whole quarter knew the day was ending…
            </div>
            <div className="mt-4 flex gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-teal-light px-3 py-1.5 text-[11px] font-semibold text-teal">
                <Wand2 size={12} /> AI polish
              </span>
              <span className="rounded-full bg-terracotta-light px-3 py-1.5 text-[11px] font-semibold text-terracotta-dark">
                Arabic ⇄ English
              </span>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-5 text-left">
          <div className="rounded-xl2 border border-border bg-panel p-6">
            <div className="mb-2 text-xs text-muted">Generating your animation</div>
            <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-border">
              <div className="h-full bg-terracotta transition-all" style={{ width: `${animPct}%` }} />
            </div>
            <div className="text-xs text-muted2">
              {animPct < 100 ? 'Painting scenes from your story…' : 'Animation ready.'}
            </div>
          </div>

          <div className="rounded-xl2 border border-border bg-panel p-6">
            <div className="mb-1 flex items-center justify-between gap-2">
              <div>
                <h3 className="font-serif text-lg">Add photos</h3>
                <p className="text-xs text-muted">
                  Upload images from this place (max 8). They attach to your story draft.
                </p>
              </div>
              <span className="text-[11px] text-muted">{photos.length}/8</span>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={onFileChange}
            />

            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`mt-4 flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 transition ${
                dragOver
                  ? 'border-terracotta bg-terracotta-light/40'
                  : 'border-border bg-cream/60'
              }`}
            >
              <ImagePlus size={28} className="mb-2 text-terracotta" />
              <p className="mb-3 text-sm text-ink2">Drag &amp; drop photos here</p>
              <PillButton
                variant="primary"
                className="!py-2 text-xs"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={photos.length >= 8}
              >
                Choose photos
              </PillButton>
            </div>

            {photos.length > 0 && (
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {photos.map((p, i) => (
                  <div key={p.id} className="group relative overflow-hidden rounded-lg border border-border">
                    <img src={p.url} alt={p.name} className="aspect-square w-full object-cover" />
                    {i === 0 && (
                      <span className="absolute left-1.5 top-1.5 rounded bg-terracotta px-1.5 py-0.5 text-[9px] font-semibold text-cream">
                        Cover
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => removePhoto(p.id)}
                      className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white opacity-90 hover:bg-black"
                      aria-label={`Remove ${p.name}`}
                    >
                      <X size={14} />
                    </button>
                    <div className="truncate bg-panel px-1.5 py-1 text-[10px] text-muted">{p.name}</div>
                  </div>
                ))}
              </div>
            )}

            {photos.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  photos.forEach((p) => URL.revokeObjectURL(p.url))
                  setPhotos([])
                }}
                className="mt-3 inline-flex items-center gap-1 text-xs text-muted hover:text-terracotta"
              >
                <Trash2 size={12} /> Clear all photos
              </button>
            )}
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="grid gap-5 text-left md:grid-cols-2">
          <div className="rounded-xl2 border border-border bg-panel p-5">
            <div className="mb-3 text-xs text-muted">Confirm the pin</div>
            <div className="relative h-40 overflow-hidden rounded-lg">
              <JordanMap
                pins={mapPins.filter((p) => p.storyId === 'echoes-of-petra')}
                focusedStoryId="echoes-of-petra"
                interactive={false}
                zoom={9}
                flyToFocused
                className="absolute inset-0"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted2">Pinned near Petra · Exact coordinates confirmed</p>
            {photos[0] && (
              <div className="mt-3 overflow-hidden rounded-lg border border-border">
                <img src={photos[0].url} alt="" className="h-28 w-full object-cover" />
                <div className="px-2 py-1.5 text-[11px] text-muted">
                  Cover photo · {photos.length} attached
                </div>
              </div>
            )}
          </div>
          <div className="rounded-xl2 border border-border bg-panel p-5">
            <div className="mb-2 text-xs text-muted">Ready to publish</div>
            <p className="mb-4 text-sm text-ink2">
              Your story will appear on the map, in the social feed, and in its regional collection.
            </p>
            <PillButton variant="teal" onClick={next}>
              <Check size={14} /> Publish story
            </PillButton>
          </div>
        </div>
      )}

      {step !== 3 && step !== 4 && (
        <div className="mt-2 flex justify-center">
          <PillButton variant="primary" onClick={next}>
            Continue <ArrowRight size={14} />
          </PillButton>
        </div>
      )}
      {step === 3 && (
        <div className="mt-6 flex justify-center">
          <PillButton
            variant="primary"
            onClick={next}
            disabled={animPct < 100}
            className={animPct < 100 ? 'cursor-not-allowed opacity-50' : ''}
          >
            Continue <ArrowRight size={14} />
          </PillButton>
        </div>
      )}

      <div className="mt-16 grid gap-8 border-t border-border pt-8 text-left md:grid-cols-3">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">Recording tips</div>
          <p className="text-[13px] leading-relaxed text-muted2">
            Seek a room with soft fabrics to reduce echo. Speak naturally, as if you are recounting
            the tale to a dear friend over tea.
          </p>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">Privacy &amp; rights</div>
          <p className="text-[13px] leading-relaxed text-muted2">
            You retain full ownership of your narrative. By publishing, you grant Hikaya the right
            to archive and present it for educational purposes.
          </p>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide">Community guardrails</div>
          <p className="text-[13px] leading-relaxed text-muted2">
            We celebrate diversity and historical accuracy. Stories must respect regional traditions
            and avoid inflammatory or harmful content.
          </p>
        </div>
      </div>

      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5 text-[11px] text-muted">
        <div>HIKAYA ARCHIVE PROJECT © 2024</div>
        <div className="flex gap-4">
          <span>Documentation</span>
          <span>Ethics Guidelines</span>
          <span>Help Center</span>
        </div>
      </footer>
    </div>
  )
}
