import { api } from './api'
export type VideoMode = 'clip' | 'narrated'
export type Soundtrack = 'narration' | 'recording'
/** What is heard in a narrated video: the story's soundtrack (ElevenLabs narration or the
 * storyteller's recording) or Omni's own generated voice and sounds. */
export type VoiceSource = 'soundtrack' | 'omni'
/** Who writes a narrated video's shot script. */
export type ScriptProvider = 'fake' | 'gemini'
/** A narrated video's refined shot script, once written. */
export interface ShotScript {
  cast: string
  setting: string
  narrator: string
  shots: { action: string; camera: string; sound: string }[]
}
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
  audio?: VoiceSource
}
/** What a narrated video will be, before anything is queued or paid for. */
export interface NarratedPlanRequest {
  story_id: string
  provider: string
  model: string
  aspect_ratio: '16:9' | '9:16'
  mode: 'narrated'
  soundtrack: Soundtrack
  audio?: VoiceSource
}
export interface NarratedPlan {
  shots: { start_ms: number; end_ms: number; seconds: number; lines: number }[]
  seconds: number
  estimate_usd: string
  lines: number
  lines_total: number
  /** False when not every line has an English translation: prompts use the spoken text. */
  english: boolean
  script?: ScriptProvider
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
  /** The shot being worked on (1-based); null when there is none. */
  shot?: number | null
  retryable?: boolean
  /** A shot's submission was never confirmed: submitting it again may be billed twice. */
  needs_confirmation?: boolean
  audio?: VoiceSource
  script?: ShotScript | null
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
  /** The default voice of a narrated video (server setting NARRATED_VIDEO_AUDIO). */
  narrated_audio?: VoiceSource
  script_provider?: ScriptProvider
}
export const getVideoConfig = () => api<VideoConfig>('/staff/videos/config')
export const getVideoJobs = () => api<VideoJobResult[]>('/staff/videos')
export const generateVideo = (payload: VideoPromptPayload): Promise<VideoJobResult> =>
  api<VideoJobResult>('/staff/videos', { body: payload })
export const planVideo = (payload: NarratedPlanRequest): Promise<NarratedPlan> =>
  api<NarratedPlan>('/staff/videos/plan', { body: payload })
/** Go on from where a narrated video stopped. `confirmResubmit` submits an unconfirmed shot
 * again, knowing it may be billed twice. */
export const retryVideo = (id: string, confirmResubmit = false): Promise<VideoJobResult> =>
  api<VideoJobResult>(
    `/staff/videos/${id}/retry`,
    confirmResubmit ? { body: { confirm_resubmit: true } } : { method: 'POST' },
  )
/** Seconds as M:SS. */
export function formatLength(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
