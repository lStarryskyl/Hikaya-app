import { api } from './api'
export interface VoiceConsent {
  version: string
  text: string
  text_ar: string
  min_seconds: number
  max_seconds: number
  /** Whether cloned voices can narrate with the current providers, and why not. */
  available: boolean
  reason: string | null
}

export type VoiceState = 'preparing' | 'ready' | 'needs_verification' | 'failed' | 'revoked'
export interface VoiceClone {
  id: string
  speaker_name: string
  status: 'queued' | 'running' | 'done' | 'failed'
  state: VoiceState
  /** What to tell staff about the state (a provider's message, a verification step). */
  message: string | null
  revoked_at: string | null
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

/** Withdraw a voice: its sample, narrations and cached speech are deleted. */
export const revokeVoice = (id: string) =>
  api<VoiceClone>(`/staff/voices/${id}/revoke`, { method: 'POST' })

/** Narrate a story in a ready cloned voice, or in the default voice again (null). */
export const chooseNarrator = (storyId: string, voiceId: string | null) =>
  api<{ id: string; narrator: string | null }>(`/staff/stories/${storyId}/narrator`, {
    method: 'PUT',
    body: { voice_id: voiceId },
  })
