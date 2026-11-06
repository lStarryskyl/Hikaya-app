import { api } from './api'
export type VideoMode = 'clip' | 'narrated'
export type Soundtrack = 'narration' | 'recording'
export interface VideoPromptPayload {
  story_id: string
  provider: string
  model: string
  prompt: string
  aspect_ratio: '16:9' | '9:16'
  seed: number
  mode?: VideoMode
  soundtrack?: Soundtrack
  subtitles?: boolean
}
/** What a narrated video will be, before anything is queued or paid for. */
export interface NarratedPlanRequest {
  story_id: string
  provider: string
  model: string
  aspect_ratio: '16:9' | '9:16'
  mode: 'narrated'
  soundtrack: Soundtrack
  subtitles: boolean
}
export interface NarratedPlan {
  shots: { start_ms: number; end_ms: number; seconds: number; lines: number }[]
  seconds: number
  estimate_usd: string
  lines: number
  lines_total: number
}
export interface VideoJobResult {
  id: string
  story_id: string
  provider: string
  model: string
  prompt: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: string
  error: string | null
  demo: boolean
  video_url: string | null
  mode?: VideoMode
  shots?: number
  seconds?: number | null
  retryable?: boolean
}
export interface VideoConfig {
  enabled: boolean
  default_provider: string
  providers: {
    id: string
    label: string
    models: string[]
    available: boolean
    reason: string
    supports_seed?: boolean
    supports_aspect?: boolean
    /** Present only for providers that can make shots of a chosen length (narrated videos). */
    max_shot_seconds?: number
  }[]
  narrated_max_seconds?: number
}
export const getVideoConfig = () => api<VideoConfig>('/staff/videos/config')
export const getVideoJobs = () => api<VideoJobResult[]>('/staff/videos')
export const generateVideo = (payload: VideoPromptPayload): Promise<VideoJobResult> =>
  api<VideoJobResult>('/staff/videos', { body: payload })
export const planVideo = (payload: NarratedPlanRequest): Promise<NarratedPlan> =>
  api<NarratedPlan>('/staff/videos/plan', { body: payload })
export const retryVideo = (id: string): Promise<VideoJobResult> =>
  api<VideoJobResult>(`/staff/videos/${id}/retry`, { method: 'POST' })
/** Seconds as M:SS. */
export function formatLength(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
