import type { Segment } from './stories'

function vttTime(ms: number) {
  return new Date(Math.max(0, ms)).toISOString().slice(11, 23)
}
/** A text track generated from the same timed words shown in the transcript. */
export function captions(segments: Segment[] = []): string {
  const cues = segments
    .map(
      (segment, i) =>
        `${i + 1}\n${vttTime(segment.start_ms)} --> ${vttTime(segment.end_ms)}\n${segment.text.replace(/-->/g, '→').replace(/\r?\n/g, ' ')}\n`,
    )
    .join('\n')
  return `data:text/vtt;charset=utf-8,${encodeURIComponent(`WEBVTT\n\n${cues}`)}`
}
