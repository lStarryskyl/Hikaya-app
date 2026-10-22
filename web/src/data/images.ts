/**
 * Place photos live in `public/places/`.
 * Prefer local files; fall back to remote only if missing.
 */

export type PhotoSlot = {
  filename: string
  place: string
  usedOn: string
}

/** Every photo slot — add files under public/places/ as {filename}.jpg|.png|.webp */
export const PHOTO_SLOTS: PhotoSlot[] = [
  { filename: 'petra-treasury-hero', place: 'Petra', usedOn: 'Home hero banner' },
  { filename: 'petra-treasury', place: 'Petra', usedOn: 'Story: The Echoes of Petra' },
  { filename: 'nabataean-water-channels', place: 'Petra', usedOn: 'Feed — Editor’s pick card' },
  { filename: 'petra-monastery', place: 'Petra', usedOn: 'Extra Petra gallery / Monastery' },
  { filename: 'petra-theater', place: 'Petra', usedOn: 'Extra Petra gallery / Theater' },
  { filename: 'petra-siq', place: 'Petra', usedOn: 'Extra Petra / Siq view' },

  { filename: 'madaba-loom', place: 'Madaba', usedOn: 'Story: The Loom of Ancestors' },
  { filename: 'mosaic-workshop', place: 'Madaba', usedOn: 'Feed post — Layla mosaic' },
  { filename: 'weaving-loom-2', place: 'Madaba', usedOn: 'Optional craft detail' },
  { filename: 'madaba-nebo', place: 'Madaba', usedOn: 'Mount Nebo gallery' },
  { filename: 'madaba-church', place: 'Madaba', usedOn: 'St George’s Church gallery' },
  { filename: 'madaba-church-facade', place: 'Madaba', usedOn: 'St George’s facade gallery' },
  { filename: 'madaba-market', place: 'Madaba', usedOn: 'Madaba craft street gallery' },

  { filename: 'balad-market', place: 'Amman / Al-Balad', usedOn: 'Story: Morning Steam in Old Al-Balad' },
  { filename: 'balad-market-2', place: 'Amman / Al-Balad', usedOn: 'Optional Al-Balad detail' },
  { filename: 'spice-market', place: 'Amman', usedOn: 'Story: Tales from the Spice Market' },
  { filename: 'amman-citadel', place: 'Amman', usedOn: 'Profile cover banner' },
  { filename: 'amman-citadel-day', place: 'Amman', usedOn: 'Citadel / Hercules gallery' },
  { filename: 'amman-roman-theater', place: 'Amman', usedOn: 'Roman Theatre gallery' },
  { filename: 'amman-rainbow', place: 'Amman', usedOn: 'Rainbow Street gallery' },
  { filename: 'amman-skyline', place: 'Amman', usedOn: 'Cityscape gallery' },
  { filename: 'amman-boulevard', place: 'Amman', usedOn: 'Abdali Boulevard gallery' },

  { filename: 'jerash-columns-dusk', place: 'Jerash', usedOn: 'Story: The Echoes of Jerash' },
  { filename: 'jerash-oval-plaza', place: 'Jerash', usedOn: 'Feed post — Oval Plaza' },
  { filename: 'ceramic-workshop', place: 'Jerash', usedOn: 'Story: The Ceramic Legacy' },
  { filename: 'jerash-sand-art', place: 'Jerash', usedOn: 'Jerash craft / sand art gallery' },

  { filename: 'wadi-rum-sunset', place: 'Wadi Rum', usedOn: 'Story: Echoes of the Red Desert' },
  { filename: 'wadi-rum-camp', place: 'Wadi Rum', usedOn: 'Bedouin camp gallery' },
  { filename: 'wadi-rum-valley', place: 'Wadi Rum', usedOn: 'Desert valley gallery' },

  { filename: 'aqaba', place: 'Aqaba', usedOn: 'Feed city circle — Aqaba waterfront' },
  { filename: 'aqaba-beach', place: 'Aqaba', usedOn: 'Beach / marina gallery' },
  { filename: 'aqaba-lagoon', place: 'Aqaba', usedOn: 'Lagoon & palms gallery' },
  { filename: 'aqaba-lionfish', place: 'Aqaba', usedOn: 'Diving — lionfish' },
  { filename: 'aqaba-tank-wreck', place: 'Aqaba', usedOn: 'Underwater museum — tank' },
  { filename: 'aqaba-armored-car', place: 'Aqaba', usedOn: 'Underwater museum — armored car' },
  { filename: 'aqaba-c130', place: 'Aqaba', usedOn: 'Underwater museum — C-130' },
]

/** Seeds that already have local files in public/places/ (updated as you add them). */
const LOCAL_FILES: Record<string, string> = {
  'petra-treasury-hero': '/places/petra-treasury-hero.png',
  'petra-treasury': '/places/petra-treasury.png',
  'nabataean-water-channels': '/places/nabataean-water-channels.png',
  'petra-monastery': '/places/petra-monastery.png',
  'petra-theater': '/places/petra-theater.png',
  'petra-siq': '/places/petra-siq.png',

  'madaba-loom': '/places/madaba-loom.png',
  'mosaic-workshop': '/places/mosaic-workshop.png',
  'weaving-loom-2': '/places/weaving-loom-2.png',
  'madaba-nebo': '/places/madaba-nebo.png',
  'madaba-church': '/places/madaba-church.png',
  'madaba-church-facade': '/places/madaba-church-facade.png',
  'madaba-market': '/places/madaba-market.png',

  'jerash-oval-plaza': '/places/jerash-oval-plaza.png',
  'jerash-columns-dusk': '/places/jerash-columns-dusk.png',
  'ceramic-workshop': '/places/ceramic-workshop.png',
  'jerash-sand-art': '/places/jerash-sand-art.png',

  'wadi-rum-sunset': '/places/wadi-rum-sunset.png',
  'wadi-rum-camp': '/places/wadi-rum-camp.png',
  'wadi-rum-valley': '/places/wadi-rum-valley.png',

  aqaba: '/places/aqaba.png',
  'aqaba-beach': '/places/aqaba-beach.png',
  'aqaba-lagoon': '/places/aqaba-lagoon.png',
  'aqaba-lionfish': '/places/aqaba-lionfish.png',
  'aqaba-tank-wreck': '/places/aqaba-tank-wreck.png',
  'aqaba-armored-car': '/places/aqaba-armored-car.png',
  'aqaba-c130': '/places/aqaba-c130.png',

  'amman-citadel': '/places/amman-citadel.png',
  'amman-citadel-day': '/places/amman-citadel-day.png',
  'balad-market': '/places/balad-market.png',
  'balad-market-2': '/places/balad-market-2.png',
  'spice-market': '/places/spice-market.png',
  'amman-rainbow': '/places/amman-rainbow.png',
  'amman-roman-theater': '/places/amman-roman-theater.png',
  'amman-skyline': '/places/amman-skyline.png',
  'amman-boulevard': '/places/amman-boulevard.png',
}

const REMOTE: Record<string, string> = {
  'petra-treasury':
    'https://images.unsplash.com/photo-1548789615-cbd185b3d8d5?auto=format&fit=crop&w={w}&h={h}&q=80',
  'petra-treasury-hero':
    'https://images.unsplash.com/photo-1580834341580-8c17e7cdd6c7?auto=format&fit=crop&w={w}&h={h}&q=80',
  'nabataean-water-channels':
    'https://images.unsplash.com/photo-1579606032821-4e6161c815c2?auto=format&fit=crop&w={w}&h={h}&q=80',
  'madaba-loom':
    'https://images.unsplash.com/photo-1564760055775-d63b17a55c44?auto=format&fit=crop&w={w}&h={h}&q=80',
  'mosaic-workshop':
    'https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Madaba_Map.jpg/1280px-Madaba_Map.jpg',
  'weaving-loom-2':
    'https://images.unsplash.com/photo-1452860606245-08bef5b24736?auto=format&fit=crop&w={w}&h={h}&q=80',
  'balad-market':
    'https://images.unsplash.com/photo-1578898886225-c7c894047899?auto=format&fit=crop&w={w}&h={h}&q=80',
  'balad-market-2':
    'https://images.unsplash.com/photo-1555881400-74d7acaacd8b?auto=format&fit=crop&w={w}&h={h}&q=80',
  'spice-market':
    'https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w={w}&h={h}&q=80',
  'amman-citadel':
    'https://images.unsplash.com/photo-1578662996442-48f60103fc96?auto=format&fit=crop&w={w}&h={h}&q=80',
  'jerash-columns-dusk':
    'https://images.unsplash.com/photo-1564507592333-c606f874c4e2?auto=format&fit=crop&w={w}&h={h}&q=80',
  'jerash-oval-plaza':
    'https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Jerash_Jordan_BW_12.JPG/1280px-Jerash_Jordan_BW_12.JPG',
  'ceramic-workshop':
    'https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w={w}&h={h}&q=80',
  'wadi-rum-sunset':
    'https://images.unsplash.com/photo-1539650116574-75c0c6d73f6e?auto=format&fit=crop&w={w}&h={h}&q=80',
  aqaba:
    'https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w={w}&h={h}&q=80',
}

const PLACE_TO_FILE: Record<string, string> = {
  Petra: 'petra-treasury',
  Madaba: 'madaba-loom',
  Amman: 'amman-citadel',
  'Al Balad': 'balad-market',
  Jerash: 'jerash-columns-dusk',
  'Wadi Rum': 'wadi-rum-sunset',
  Aqaba: 'aqaba',
}

function applySize(url: string, w: number, h: number) {
  if (url.includes('{w}')) return url.replace('{w}', String(w)).replace('{h}', String(h))
  return url
}

function resolveSeed(seed: string, place?: string) {
  if (LOCAL_FILES[seed] || REMOTE[seed]) return seed
  if (place) {
    const match = Object.entries(PLACE_TO_FILE).find(([p]) =>
      place.toLowerCase().includes(p.toLowerCase()),
    )
    if (match) return match[1]
  }
  return seed
}

export function imageUrl(seed: string, w = 800, h = 600, place?: string) {
  const key = resolveSeed(seed, place)
  if (LOCAL_FILES[key]) return LOCAL_FILES[key]
  const remote = REMOTE[key] ?? REMOTE['petra-treasury']
  return applySize(remote, w, h)
}

export function avatarUrl(seed: string, size = 80) {
  return `https://i.pravatar.cc/${size}?u=${encodeURIComponent(seed)}`
}

export function placeCircleImage(placeName: string, size = 120) {
  const lower = placeName.toLowerCase()
  if (lower === 'petra') {
    return LOCAL_FILES['petra-treasury'] ?? imageUrl('petra-treasury', size, size, 'Petra')
  }
  if (lower === 'madaba') {
    return LOCAL_FILES['madaba-loom'] ?? imageUrl('madaba-loom', size, size, 'Madaba')
  }
  if (lower === 'jerash') {
    return (
      LOCAL_FILES['jerash-columns-dusk'] ??
      LOCAL_FILES['jerash-oval-plaza'] ??
      imageUrl('jerash-columns-dusk', size, size, 'Jerash')
    )
  }
  if (lower === 'amman') {
    return LOCAL_FILES['amman-citadel'] ?? imageUrl('amman-citadel', size, size, 'Amman')
  }
  if (lower === 'wadi rum') {
    return LOCAL_FILES['wadi-rum-sunset'] ?? imageUrl('wadi-rum-sunset', size, size, 'Wadi Rum')
  }
  if (lower === 'aqaba') {
    return LOCAL_FILES.aqaba ?? imageUrl('aqaba', size, size, 'Aqaba')
  }
  const file = PLACE_TO_FILE[placeName] ?? placeName.toLowerCase().replace(/\s+/g, '-')
  return imageUrl(file, size, size, placeName)
}

/** Local galleries by place for story player. */
export const PETRA_GALLERY = [
  LOCAL_FILES['petra-treasury-hero'],
  LOCAL_FILES['petra-treasury'],
  LOCAL_FILES['petra-monastery'],
  LOCAL_FILES['petra-theater'],
  LOCAL_FILES['nabataean-water-channels'],
  LOCAL_FILES['petra-siq'],
].filter(Boolean) as string[]

export const MADABA_GALLERY = [
  LOCAL_FILES['madaba-loom'],
  LOCAL_FILES['weaving-loom-2'],
  LOCAL_FILES['mosaic-workshop'],
  LOCAL_FILES['madaba-nebo'],
  LOCAL_FILES['madaba-church'],
  LOCAL_FILES['madaba-church-facade'],
  LOCAL_FILES['madaba-market'],
].filter(Boolean) as string[]

export const AMMAN_GALLERY = [
  LOCAL_FILES['amman-citadel'],
  LOCAL_FILES['amman-citadel-day'],
  LOCAL_FILES['amman-roman-theater'],
  LOCAL_FILES['balad-market'],
  LOCAL_FILES['balad-market-2'],
  LOCAL_FILES['spice-market'],
  LOCAL_FILES['amman-rainbow'],
  LOCAL_FILES['amman-skyline'],
  LOCAL_FILES['amman-boulevard'],
].filter(Boolean) as string[]

export const JERASH_GALLERY = [
  LOCAL_FILES['jerash-columns-dusk'],
  LOCAL_FILES['jerash-oval-plaza'],
  LOCAL_FILES['ceramic-workshop'],
  LOCAL_FILES['jerash-sand-art'],
].filter(Boolean) as string[]

export const WADI_RUM_GALLERY = [
  LOCAL_FILES['wadi-rum-sunset'],
  LOCAL_FILES['wadi-rum-camp'],
  LOCAL_FILES['wadi-rum-valley'],
].filter(Boolean) as string[]

export const AQABA_GALLERY = [
  LOCAL_FILES.aqaba,
  LOCAL_FILES['aqaba-beach'],
  LOCAL_FILES['aqaba-lagoon'],
  LOCAL_FILES['aqaba-lionfish'],
  LOCAL_FILES['aqaba-tank-wreck'],
  LOCAL_FILES['aqaba-armored-car'],
  LOCAL_FILES['aqaba-c130'],
].filter(Boolean) as string[]

export function galleryForPlace(place: string): string[] {
  if (place === 'Petra') return PETRA_GALLERY
  if (place === 'Madaba') return MADABA_GALLERY
  if (place === 'Amman' || place === 'Al Balad') return AMMAN_GALLERY
  if (place === 'Jerash') return JERASH_GALLERY
  if (place === 'Wadi Rum') return WADI_RUM_GALLERY
  if (place === 'Aqaba') return AQABA_GALLERY
  return []
}
