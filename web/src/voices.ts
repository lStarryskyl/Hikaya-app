import { api } from './api'
export interface VoiceConsent {
  version: string
  text: string
  text_ar: string
  min_seconds: number
  max_seconds: number
}
export interface VoiceClone {
  id: string
  speaker_name: string
  status: 'queued' | 'running' | 'done' | 'failed'
  error: string | null
  demo: boolean
  requires_verification: boolean
  voice_id: string | null
  sample_url: string
  duration_ms: number
  consent: { version: string; text: string; at: string; speaker_name: string }
}
export const getVoiceConsent = () => api<VoiceConsent>('/staff/voices/consent')
export const getVoices = () => api<VoiceClone[]>('/staff/voices')
export function cloneVoice(
  file: File,
  speaker: string,
  consent: VoiceConsent,
  locale: string,
  requestId: string,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('speaker_name', speaker)
  form.append('consent_version', consent.version)
  form.append('locale', locale)
  for (const key of ['speaker_confirmed', 'rights_confirmed', 'use_confirmed'])
    form.append(key, 'true')
  form.append('request_id', requestId)
  return api<VoiceClone>('/staff/voices', { form })
}
