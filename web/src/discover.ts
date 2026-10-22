import { api } from './api'
import type { CategoryValue } from './stories'

/** A place photo, stored as WebP at several widths. `urls` maps width to URL. */
export interface Photo {
  slug: string
  caption: string
  urls: Record<string, string>
}

export interface StoryCard {
  id: string
  title: string
  category: CategoryValue | null
  place_name: string
  latitude: number | null
  longitude: number | null
  duration_ms: number | null
  published_at: string | null
  curated: boolean
  author: { id: string; display_name: string }
  excerpt: string
  cover: Photo | null
}

export interface FeedPage {
  items: StoryCard[]
  next_cursor: string | null
}

export type PinKind = 'featured' | 'recent' | 'ordinary'

export interface Pin {
  story_id: string
  title: string
  place_name: string
  category: CategoryValue | null
  latitude: number
  longitude: number
  kind: PinKind
}

export interface Place {
  slug: string
  name: string
  latitude: number
  longitude: number
  cover: Photo | null
  photos: Photo[]
  story_count: number
}

export function getFeed({ limit = 12, cursor }: { limit?: number; cursor?: string | null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return api<FeedPage>(`/stories?${params}`)
}

export const getPins = () => api<Pin[]>('/map/pins')

// Places change only when the demo data is reloaded, so one request per page load is enough.
let placesRequest: Promise<Place[]> | null = null
export function getPlaces(): Promise<Place[]> {
  placesRequest ??= api<Place[]>('/places').catch((e) => {
    placesRequest = null
    throw e
  })
  return placesRequest
}

/** The smallest stored width that is at least `width`, else the largest. */
export function photoUrl(photo: Photo | null | undefined, width = 960): string | undefined {
  if (!photo) return undefined
  const widths = Object.keys(photo.urls).map(Number).sort((a, b) => a - b)
  const pick = widths.find((w) => w >= width) ?? widths[widths.length - 1]
  return photo.urls[String(pick)]
}

export function photoSrcSet(photo: Photo): string {
  return Object.entries(photo.urls)
    .map(([w, url]) => `${url} ${w}w`)
    .join(', ')
}

export function findPhoto(places: Place[] | null | undefined, slug: string): Photo | undefined {
  return places?.flatMap((p) => p.photos).find((p) => p.slug === slug)
}

export function timeAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000))
  if (minutes < 60) return minutes <= 1 ? 'just now' : `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  const months = Math.round(days / 30)
  return `${months} month${months === 1 ? '' : 's'} ago`
}
