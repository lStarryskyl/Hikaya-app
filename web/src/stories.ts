import { api } from './api'

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

export type StepName = 'transcribe' | 'polish' | 'translate_en' | 'translate_msa'

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

export interface StoryRecord {
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
}

export type StoryFields = Partial<
  Pick<StoryRecord, 'title' | 'category' | 'place_name' | 'latitude' | 'longitude' | 'original_language'>
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

/** Story ids from the API are UUIDs; the remaining mock stories use readable slugs. */
export function isStoryId(id: string | undefined): id is string {
  return !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
}

export function formatDuration(ms: number | null): string {
  if (!ms) return ''
  const total = Math.round(ms / 1000)
  return total < 60 ? `${total} sec` : `${Math.round(total / 60)} min`
}

export const getStory = (id: string) => api<StoryRecord>(`/stories/${id}`)
export const createStory = (fields: StoryFields = {}) => api<StoryRecord>('/stories', { body: fields })
export const updateStory = (id: string, fields: StoryFields) =>
  api<StoryRecord>(`/stories/${id}`, { method: 'PATCH', body: fields })
export const submitStory = (id: string) => api<StoryRecord>(`/stories/${id}/submit`, { method: 'POST' })

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
