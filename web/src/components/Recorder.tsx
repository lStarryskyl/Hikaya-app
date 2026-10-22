import { useEffect, useRef, useState } from 'react'
import { Mic, Pause, Play, RotateCcw, Square } from 'lucide-react'
import { PillButton } from './ui'

/** Formats browsers can record, best first. */
const FORMATS = [
  { mime: 'audio/webm;codecs=opus', label: 'WebM · Opus', ext: 'webm' },
  { mime: 'audio/ogg;codecs=opus', label: 'Ogg · Opus', ext: 'ogg' },
  { mime: 'audio/mp4', label: 'MP4 · AAC', ext: 'm4a' },
  { mime: 'audio/webm', label: 'WebM', ext: 'webm' },
]

export function recordingFormat() {
  if (typeof MediaRecorder === 'undefined') return null
  return FORMATS.find((f) => MediaRecorder.isTypeSupported(f.mime)) ?? null
}

const BARS = 15

function microphoneMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError')
    return 'Microphone access is blocked. Allow it in your browser’s site settings, or upload a file instead.'
  if (name === 'NotFoundError' || name === 'OverconstrainedError')
    return 'No microphone was found. Connect one, or upload a recording instead.'
  if (name === 'NotSupportedError')
    return 'Recording is not supported here. Upload a recording instead.'
  if (name === 'NotReadableError')
    return 'The microphone is in use by another app. Close it and try again.'
  return 'The microphone could not be started. You can upload a recording instead.'
}

type State = 'idle' | 'recording' | 'paused'

/**
 * Records with the browser's own MediaRecorder. Shows a timer and a live level meter, and
 * hands the finished recording to `onRecorded` when the member presses Finish.
 */
export default function Recorder({
  onRecorded,
  disabled = false,
}: {
  onRecorded: (file: File) => void
  disabled?: boolean
}) {
  const format = recordingFormat()
  const [state, setState] = useState<State>('idle')
  const [seconds, setSeconds] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0.15))
  const [error, setError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const stream = useRef<MediaStream | null>(null)
  const audio = useRef<{ ctx: AudioContext; frame: number } | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const discard = useRef(false)
  // "Start again" waits for the old recorder to finish stopping before a new one starts.
  const restartPending = useRef(false)

  function stopEverything() {
    window.clearInterval(timer.current)
    if (audio.current) {
      cancelAnimationFrame(audio.current.frame)
      void audio.current.ctx.close()
      audio.current = null
    }
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    setLevels(Array(BARS).fill(0.15))
  }

  useEffect(
    () => () => {
      discard.current = true
      if (recorder.current?.state !== 'inactive') recorder.current?.stop()
      stopEverything()
    },
    [],
  )

  function meter(media: MediaStream) {
    const ctx = new AudioContext()
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 64
    ctx.createMediaStreamSource(media).connect(analyser)
    const data = new Uint8Array(analyser.frequencyBinCount)
    const tick = () => {
      analyser.getByteFrequencyData(data)
      setLevels(Array.from({ length: BARS }, (_, i) => Math.max(0.12, data[i + 1] / 255)))
      if (audio.current) audio.current.frame = requestAnimationFrame(tick)
    }
    audio.current = { ctx, frame: requestAnimationFrame(tick) }
  }

  async function start() {
    setError('')
    if (!format || !navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot record audio. Upload a recording instead.')
      return
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      setError(microphoneMessage(e))
      return
    }
    chunks.current = []
    discard.current = false
    const rec = new MediaRecorder(stream.current, { mimeType: format.mime })
    rec.ondataavailable = (e) => e.data.size > 0 && chunks.current.push(e.data)
    rec.onstop = () => {
      stopEverything()
      if (restartPending.current) {
        restartPending.current = false
        void start()
        return
      }
      if (discard.current) return
      const type = format.mime.split(';')[0]
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
      onRecorded(new File(chunks.current, `recording-${stamp}.${format.ext}`, { type }))
    }
    rec.start(1000)
    recorder.current = rec
    meter(stream.current)
    setSeconds(0)
    timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    setState('recording')
  }

  function pause() {
    recorder.current?.pause()
    window.clearInterval(timer.current)
    setState('paused')
  }

  function resume() {
    recorder.current?.resume()
    timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    setState('recording')
  }

  function finish() {
    recorder.current?.stop()
    setState('idle')
  }

  function restart() {
    discard.current = true
    restartPending.current = true
    setSeconds(0)
    recorder.current?.stop()
  }

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  const live = state !== 'idle'

  return (
    <div className="flex flex-col items-center rounded-xl2 border border-border bg-panel p-8">
      <div className="mb-6 flex h-16 items-end gap-1" aria-hidden>
        {levels.map((level, i) => (
          <span
            key={i}
            className={`w-1.5 rounded-full ${state === 'recording' ? 'bg-terracotta' : 'bg-terracotta/40'}`}
            style={{ height: `${Math.round(level * 100)}%`, transition: 'height .08s linear' }}
          />
        ))}
      </div>
      <div className="mb-1 font-serif text-3xl" aria-live="off">
        {mm}:{ss}
      </div>
      <div className="mb-5 text-[11px] text-muted" role="status">
        {state === 'recording' ? 'Recording…' : state === 'paused' ? 'Paused' : format ? `Records as ${format.label}` : 'Recording is not available in this browser'}
      </div>

      {!live ? (
        <button
          type="button"
          onClick={() => void start()}
          disabled={disabled}
          aria-label="Start recording"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-terracotta text-cream transition hover:brightness-105 disabled:opacity-50"
        >
          <Mic size={22} />
        </button>
      ) : (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={restart}
            aria-label="Start again"
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border text-ink2 hover:bg-cream"
          >
            <RotateCcw size={16} />
          </button>
          <button
            type="button"
            onClick={state === 'recording' ? pause : resume}
            aria-label={state === 'recording' ? 'Pause recording' : 'Resume recording'}
            className="flex h-16 w-16 items-center justify-center rounded-full bg-terracotta-dark text-cream"
          >
            {state === 'recording' ? <Pause size={22} /> : <Play size={22} />}
          </button>
          <PillButton type="button" variant="teal" onClick={finish} className="!py-2.5">
            <Square size={13} /> Finish
          </PillButton>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-4 max-w-sm rounded-lg bg-terracotta-light px-3 py-2 text-center text-sm text-terracotta-dark">
          {error}
        </p>
      )}
    </div>
  )
}
