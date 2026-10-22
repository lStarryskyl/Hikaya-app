import { useEffect, useImperativeHandle, useRef, forwardRef } from 'react'
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { MapPin } from '../types'
import { stories } from '../data/mock'

const JORDAN_CENTER: [number, number] = [36.0, 31.3]

const KIND_COLOR: Record<MapPin['kind'], string> = {
  featured: '#B85C38',
  dense: '#C08A2E',
  recent: '#1F7A63',
}

function pinElement(kind: MapPin['kind'], active: boolean) {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = 'hikaya-map-pin'
  el.style.cssText = [
    'width:18px',
    'height:18px',
    'border-radius:9999px',
    `background:${KIND_COLOR[kind]}`,
    `border:${active ? '3px' : '2px'} solid #fff`,
    'box-shadow:0 1px 6px rgba(0,0,0,.35)',
    'cursor:pointer',
    'padding:0',
    active ? 'transform:scale(1.25)' : '',
  ].join(';')
  return el
}

export interface JordanMapHandle {
  zoomIn: () => void
  zoomOut: () => void
  reset: () => void
  flyTo: (lng: number, lat: number, zoom?: number) => void
}

interface JordanMapProps {
  pins: MapPin[]
  focusedStoryId?: string | null
  onSelectStory?: (storyId: string) => void
  className?: string
  interactive?: boolean
  zoom?: number
  flyToFocused?: boolean
  showNavControl?: boolean
}

const JordanMap = forwardRef<JordanMapHandle, JordanMapProps>(function JordanMap(
  {
    pins,
    focusedStoryId = null,
    onSelectStory,
    className = '',
    interactive = true,
    zoom = 6.5,
    flyToFocused = true,
    showNavControl = false,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markersRef = useRef<Marker[]>([])
  const onSelectRef = useRef(onSelectStory)
  onSelectRef.current = onSelectStory

  useImperativeHandle(ref, () => ({
    zoomIn: () => mapRef.current?.zoomIn(),
    zoomOut: () => mapRef.current?.zoomOut(),
    reset: () => mapRef.current?.flyTo({ center: JORDAN_CENTER, zoom, speed: 1.2 }),
    flyTo: (lng, lat, z = 9) => mapRef.current?.flyTo({ center: [lng, lat], zoom: z, speed: 1.2 }),
  }))

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: JORDAN_CENTER,
      zoom,
      interactive,
      attributionControl: { compact: true },
    })

    if (interactive && showNavControl) {
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    }

    mapRef.current = map

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []
      map.remove()
      mapRef.current = null
    }
  }, [interactive, zoom, showNavControl])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    pins.forEach((pin) => {
      const story = stories.find((s) => s.id === pin.storyId)
      const el = pinElement(pin.kind, pin.storyId === focusedStoryId)
      el.setAttribute('aria-label', story?.title ?? pin.storyId)
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        onSelectRef.current?.(pin.storyId)
      })

      const marker = new Marker({ element: el }).setLngLat([pin.lng, pin.lat]).addTo(map)
      markersRef.current.push(marker)
    })
  }, [pins, focusedStoryId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyToFocused || !focusedStoryId) return
    const pin = pins.find((p) => p.storyId === focusedStoryId)
    if (!pin) return
    map.flyTo({ center: [pin.lng, pin.lat], zoom: Math.max(map.getZoom(), 8), speed: 1.2 })
  }, [focusedStoryId, pins, flyToFocused])

  return <div ref={containerRef} className={`h-full w-full min-h-[240px] ${className}`} />
})

export default JordanMap
