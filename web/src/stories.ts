import { api } from './api'

export type CategoryValue = 'crafts' | 'daily_life' | 'folklore' | 'history' | 'personal'
export type LanguageValue = 'jordanian' | 'msa' | 'english'
export type StoryStatus = 'draft' | 'moderating' | 'published' | 'held' | 'needs_edit'

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
