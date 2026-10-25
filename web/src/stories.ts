import { message, number } from './i18n'
import { api } from './api'
import type { Photo } from './discover'

export type CategoryValue = 'crafts' | 'daily_life' | 'folklore' | 'history' | 'personal'
export type LanguageValue = 'jordanian' | 'msa' | 'english'
export type StoryStatus = 'draft' | 'moderating' | 'published' | 'held' | 'needs_edit'

export type LayerKind = 'verbatim' | 'polished' | 'translation_en' | 'translation_msa'

export interface Segment {
  start_ms: number
  end_ms: number
  text: string
}

export interface TextLayer {
  kind: LayerKind
  language: LanguageValue
  edited: boolean
  segments: Segment[]
}

export type StepName =
  'transcribe' | 'polish' | 'translate_en' | 'translate_msa' | 'moderate' | 'narrate' | 'slideshow'

export type NarrationSource = 'polished' | 'msa'

/** Made after submitting, from the finished text; the player shows their progress. */
export const MEDIA_STEPS: StepName[] = ['narrate', 'slideshow']

export interface Narration {
  url: string
  content_type: string
  voice: string
  language: LanguageValue
  source: NarrationSource
  timing: 'alignment' | 'per_segment'
  /** One per line of the text read, in the narration's own time. */
  segments: Segment[]
  /** The consenting person whose cloned voice read it; null for the default voice. */
  narrated_by?: string | null
}

export interface PipelineStep {
  step: StepName
  /** waiting: not started, because an earlier step has not finished. */
  status: 'waiting' | 'queued' | 'running' | 'done' | 'failed'
  message: string
}

export interface PipelineStatus {
  steps: PipelineStep[]
  complete: boolean
}

export interface StoryPhoto {
  id: string
  source: 'upload' | 'gallery'
  photo: Photo
}

export interface ConsentStatement {
  version: string
  text: string
}

export interface StoryRecord {
  tags: string[]
  id: string
  title: string
  category: CategoryValue | null
  place_name: string
  latitude: number | null
  longitude: number | null
  original_language: LanguageValue | null
  duration_ms: number | null
  status: StoryStatus
  published_at: string | null
  created_at: string
  author: { id: string; display_name: string }
  audio: { url: string; content_type: string; original_url: string } | null
  layers: TextLayer[]
  place_slug: string | null
  cover: Photo | null
  curated: boolean
  photos: StoryPhoto[]
  consent: { version: string; at: string } | null
  narration_source: NarrationSource
  narration: Narration | null
  slideshow: { url: string; content_type: string } | null
  /** A pre-made AI video sample (seeded stories only); locked unless premium or staff. */
  ai_video?: {
    sample_id: string
    title: string
    credit: string
    source_url: string
    note: string
    poster_url: string
    locked: boolean
    video_url: string | null
  } | null
  /** The cloned voice chosen to narrate it (author and staff only). */
  narrator_voice_id?: string | null
  /** Only for the author and staff. */
  moderation: {
    held: boolean
    labels: { label: ModerationLabel; raised: boolean; reason: string }[]
    judged_at: string
  } | null
  review: { note: string | null; at: string | null } | null
}

export type ModerationLabel = 'hate' | 'violence' | 'sexual' | 'other_terrible'

export const MODERATION_LABELS: Record<ModerationLabel, string> = {
  hate: 'Hateful content',
  violence: 'Violence',
  sexual: 'Sexual content',
  other_terrible: 'Other harmful content',
}

export const STATUS_LABELS: Record<StoryStatus, string> = {
  draft: 'Draft',
  moderating: 'Being checked',
  published: 'Published',
  held: 'Under review',
  needs_edit: 'Needs your edits',
}

/** One row of "My stories". */
export interface MyStory {
  id: string
  title: string
  status: StoryStatus
  place_name: string
  cover: Photo | null
  updated_at: string
  published_at: string | null
  held_for: ModerationLabel[]
  review_note: string | null
}

export const getMyStories = () => api<MyStory[]>('/me/stories')
export const deleteStory = (id: string) => api<void>(`/stories/${id}`, { method: 'DELETE' })

export type StoryFields = Partial<
  Pick<
    StoryRecord,
    | 'title'
    | 'category'
    | 'place_name'
    | 'latitude'
    | 'longitude'
    | 'original_language'
    | 'narration_source'
    | 'tags'
  >
>

export const CATEGORY_LABELS: Record<CategoryValue, string> = {
  crafts: 'Crafts',
  daily_life: 'Daily Life',
  folklore: 'Folklore',
  history: 'History',
  personal: 'Personal',
}

export const LANGUAGE_LABELS: Record<LanguageValue, string> = {
  jordanian: 'Jordanian Arabic',
  msa: 'Modern Standard Arabic',
  english: 'English',
}

export const LAYER_LABELS: Record<LayerKind, string> = {
  verbatim: 'Original words',
  polished: 'Polished',
  translation_en: 'English',
  translation_msa: 'Modern Standard Arabic',
}

export const STEP_LABELS: Record<StepName, string> = {
  transcribe: 'Transcribing the recording',
  polish: 'Polishing the text',
  translate_en: 'Translating to English',
  translate_msa: 'Translating to Modern Standard Arabic',
  moderate: 'Checking the story before publishing',
  narrate: 'Recording the narration',
  slideshow: 'Making the slideshow',
}

/** Same limit as the API's per-line maximum. */
export const MAX_SEGMENT_CHARS = 2000

/** Arabic text (dialect or MSA) is laid out right to left. */
export function textDirection(language: LanguageValue): { dir: 'rtl' | 'ltr'; lang: string } {
  return language === 'english' ? { dir: 'ltr', lang: 'en' } : { dir: 'rtl', lang: 'ar' }
}

/** The font class for text in this language. */
export function textFont(language: LanguageValue): string {
  return language === 'english' ? '' : 'font-arabic'
}

export function hasTranscript(story: StoryRecord | null): boolean {
  const kinds = new Set(story?.layers.map((l) => l.kind))
  return kinds.has('verbatim') && kinds.has('polished')
}

export function timestamp(ms: number): string {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** Story ids are UUIDs; anything else in a story link cannot be a story. */
export function isStoryId(id: string | undefined): id is string {
  return !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
}

export function formatDuration(ms: number | null): string {
  if (!ms) return ''
  const total = Math.round(ms / 1000)
  return total < 60
    ? message('{count} sec', { count: number(total) })
    : message('{count} min', { count: number(Math.round(total / 60)) })
}

export const getStory = (id: string) => api<StoryRecord>(`/stories/${id}`)
export const createStory = (fields: StoryFields = {}) =>
  api<StoryRecord>('/stories', { body: fields })
export const updateStory = (id: string, fields: StoryFields) =>
  api<StoryRecord>(`/stories/${id}`, { method: 'PATCH', body: fields })
export const submitStory = (id: string, consentVersion: string) =>
  api<StoryRecord>(`/stories/${id}/submit`, {
    body: { consent: true, consent_version: consentVersion },
  })

export const getConsent = () => api<ConsentStatement>('/stories/consent')

/** The limits the API checks uploads against, served so the page shows the same numbers. */
export interface UploadLimits {
  audio_max_mb: number
  audio_max_minutes: number
  photo_types: string[]
  photo_max_mb: number
  photos_per_story: number
}

let limitsRequest: Promise<UploadLimits> | null = null
export function getLimits(): Promise<UploadLimits> {
  limitsRequest ??= api<UploadLimits>('/stories/limits').catch((e) => {
    limitsRequest = null
    throw e
  })
  return limitsRequest
}

export function addPhoto(id: string, file: File) {
  const form = new FormData()
  form.append('file', file, file.name)
  return api<StoryPhoto>(`/stories/${id}/photos`, { method: 'POST', form })
}
export const pickGalleryPhoto = (id: string, slug: string) =>
  api<StoryPhoto>(`/stories/${id}/photos/gallery`, { body: { slug } })
export const reorderPhotos = (id: string, ids: string[]) =>
  api<StoryPhoto[]>(`/stories/${id}/photos/order`, { method: 'PUT', body: { ids } })
export const deletePhoto = (id: string, photoId: string) =>
  api<void>(`/stories/${id}/photos/${photoId}`, { method: 'DELETE' })

export async function uploadAudio(id: string, file: Blob, filename: string): Promise<StoryRecord> {
  const form = new FormData()
  form.append('file', file, filename)
  return api<StoryRecord>(`/stories/${id}/audio`, { method: 'PUT', form })
}

export const getPipeline = (id: string) => api<PipelineStatus>(`/stories/${id}/pipeline`)
export const retryStep = (id: string, step: StepName) =>
  api<PipelineStatus>(`/stories/${id}/pipeline/${step}/retry`, { method: 'POST' })
export const editLayer = (id: string, kind: LayerKind, texts: string[]) =>
  api<StoryRecord>(`/stories/${id}/layers/${kind}`, { method: 'PATCH', body: { texts } })
