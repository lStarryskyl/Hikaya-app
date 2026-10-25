import { currentLocale, t } from './i18n'
import { api } from './api'
import type { CategoryValue } from './stories'

/** A place photo, stored as WebP at several widths. `urls` maps width to URL. */
export interface Photo {
  slug: string
  caption: string
  urls: Record<string, string>
}

export interface StoryCard {
  tags: string[]
  distance_km: number | null
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
  /** How many stories match, across all pages. */
  total: number
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

export interface DiscoveryFilters {
  q?: string
  category?: CategoryValue[]
  tag?: string[]
  curated?: boolean
  latitude?: number
  longitude?: number
  radius_km?: number
}

export function discoveryParams(filters: DiscoveryFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  filters.category?.forEach((value) => params.append('category', value))
  filters.tag?.forEach((value) => params.append('tag', value))
  if (filters.curated) params.set('curated', 'true')
  if (filters.latitude !== undefined && filters.longitude !== undefined) {
    params.set('latitude', String(filters.latitude))
    params.set('longitude', String(filters.longitude))
    params.set('radius_km', String(filters.radius_km ?? 25))
  }
  return params
}

export function getFeed({
  limit = 12,
  cursor,
  ...filters
}: DiscoveryFilters & {
  limit?: number
  cursor?: string | null
} = {}) {
  const params = discoveryParams(filters)
  params.set('limit', String(limit))
  if (cursor) params.set('cursor', cursor)
  return api<FeedPage>(`/stories?${params}`)
}

export const getPins = (filters: DiscoveryFilters = {}) =>
  api<Pin[]>(`/map/pins?${discoveryParams(filters)}`)

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
  const widths = Object.keys(photo.urls)
    .map(Number)
    .sort((a, b) => a - b)
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
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  const formatter = new Intl.RelativeTimeFormat(currentLocale(), { numeric: 'auto' })
  if (seconds < 60) return t('just now')
  if (seconds < 3600) return formatter.format(-Math.round(seconds / 60), 'minute')
  if (seconds < 86400) return formatter.format(-Math.round(seconds / 3600), 'hour')
  if (seconds < 2592000) return formatter.format(-Math.round(seconds / 86400), 'day')
  return formatter.format(-Math.round(seconds / 2592000), 'month')
}
