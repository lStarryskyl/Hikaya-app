export interface Story {
  id: string
  title: string
  category: 'Crafts' | 'Daily Life' | 'Folklore' | 'History' | 'Personal'
  place: string
  narrator: string
  narratorAvatarSeed: string
  duration: string
  excerpt: string
  imageSeed: string
  likes: number
  comments: number
}

export interface MapPin {
  id: string
  storyId: string
  lat: number
  lng: number
  kind: 'featured' | 'dense' | 'recent'
  /** Optional % fallback for non-map preview layouts */
  x?: number
  y?: number
}

export interface TranscriptLine {
  time: string
  text: string
  highlighted?: boolean
}

export interface Comment {
  name: string
  avatarSeed: string
  timeAgo: string
  text: string
  likes: number
}

export interface FeedPost {
  id: string
  name: string
  place: string
  avatarSeed: string
  imageSeed: string
  likes: number
  comments: number
  caption: string
  timeAgo: string
  liked?: boolean
  saved?: boolean
}
