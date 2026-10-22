import type { Pin, PinKind } from './discover'

/** A pin as the map component draws it. */
export interface MapPin {
  id: string
  storyId: string
  lat: number
  lng: number
  kind: PinKind
  /** Accessible name for the pin, usually the story title. */
  label: string
}

export function toMapPins(pins: Pin[]): MapPin[] {
  return pins.map((p) => ({
    id: p.story_id,
    storyId: p.story_id,
    lat: p.latitude,
    lng: p.longitude,
    kind: p.kind,
    label: p.title,
  }))
}
