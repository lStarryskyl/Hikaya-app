import { useEffect, useRef, useState } from 'react'
import { LAYER_LABELS, textDirection, timestamp, type LayerKind, type TextLayer } from '../stories'

/**
 * The player's transcript: pick a version, follow along as the line being spoken is
 * highlighted, and tap a line to jump there. All versions share the same timestamps.
 */
export default function TranscriptView({
  layers,
  elapsedMs,
  following,
  onSeek,
}: {
  layers: TextLayer[]
  elapsedMs: number
  following: boolean
  onSeek: (ms: number) => void
}) {
  const [kind, setKind] = useState<LayerKind>(
    layers.some((l) => l.kind === 'polished') ? 'polished' : layers[0].kind,
  )
  const layer = layers.find((l) => l.kind === kind) ?? layers[0]
  const activeIndex = layer.segments.findIndex((s) => elapsedMs >= s.start_ms && elapsedMs < s.end_ms)
  const activeRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Scroll only the transcript list (scrollIntoView would also move the page).
  useEffect(() => {
    const line = activeRef.current
    const list = listRef.current
    if (!following || !line || !list) return
    const above = line.offsetTop < list.scrollTop
    const below = line.offsetTop + line.offsetHeight > list.scrollTop + list.clientHeight
    if (above || below) list.scrollTo({ top: line.offsetTop - 16, behavior: 'smooth' })
  }, [activeIndex, following])

  const direction = textDirection(layer.language)
  return (
    <div className="mb-4">
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Transcript language">
        {layers.map((l) => (
          <button
            key={l.kind}
            type="button"
            role="tab"
            aria-selected={l.kind === layer.kind}
            onClick={() => setKind(l.kind)}
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              l.kind === layer.kind ? 'bg-terracotta text-cream' : 'bg-cream text-muted2 hover:bg-border'
            }`}
          >
            {LAYER_LABELS[l.kind]}
          </button>
        ))}
      </div>
      <div ref={listRef} className="relative max-h-[420px] space-y-1.5 overflow-y-auto pe-1 scrollbar-thin">
        {layer.segments.map((seg, i) => {
          const active = i === activeIndex
          return (
            <button
              key={seg.start_ms}
              ref={active ? activeRef : undefined}
              type="button"
              onClick={() => onSeek(seg.start_ms)}
              aria-current={active ? 'true' : undefined}
              aria-label={`Play from ${timestamp(seg.start_ms)}`}
              className={`block w-full rounded-lg p-3 text-start text-[12.5px] leading-relaxed transition ${
                active
                  ? 'border-s-2 border-terracotta bg-terracotta-light text-ink2'
                  : 'text-muted2 hover:bg-cream'
              }`}
            >
              <span className="me-2 font-mono text-[10px] text-terracotta">{timestamp(seg.start_ms)}</span>
              <span {...direction} className={`${layer.language === 'english' ? '' : 'font-arabic'} block`}>
                {seg.text}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
