import { api } from './api'
export interface VideoPromptPayload {
  story_id: string
  provider: string
  model: string
  prompt: string
  aspect_ratio: '16:9' | '9:16'
  seed: number
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
  }[]
}
export const getVideoConfig = () => api<VideoConfig>('/staff/videos/config')
export const getVideoJobs = () => api<VideoJobResult[]>('/staff/videos')
export const generateVideo = (payload: VideoPromptPayload): Promise<VideoJobResult> =>
  api<VideoJobResult>('/staff/videos', { body: payload })
