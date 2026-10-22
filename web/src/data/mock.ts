import { Story, MapPin, TranscriptLine, Comment, FeedPost } from '../types'

export const stories: Story[] = [
  {
    id: 'loom-of-ancestors',
    title: 'The Loom of Ancestors',
    category: 'Crafts',
    place: 'Madaba',
    narrator: 'um ahmad',
    narratorAvatarSeed: 'um-ahmad',
    duration: '12 min',
    excerpt: 'Preserving the geometry of the past, one thread at a time.',
    imageSeed: 'madaba-loom',
    likes: 1242,
    comments: 48,
  },
  {
    id: 'morning-steam',
    title: 'Morning Steam in Old Al-Balad',
    category: 'Daily Life',
    place: 'Al Balad',
    narrator: 'zaid j.',
    narratorAvatarSeed: 'zaid-j',
    duration: '8 min',
    excerpt: 'The tea vendors of downtown Amman open before the sun.',
    imageSeed: 'balad-market',
    likes: 890,
    comments: 32,
  },
  {
    id: 'echoes-red-desert',
    title: 'Echoes of the Red Desert',
    category: 'Folklore',
    place: 'Wadi Rum',
    narrator: 'faisal b.',
    narratorAvatarSeed: 'faisal-b',
    duration: '15 min',
    excerpt: 'Under a Bedouin tent, the stars have names older than maps.',
    imageSeed: 'wadi-rum-sunset',
    likes: 2044,
    comments: 61,
  },
  {
    id: 'echoes-of-jerash',
    title: 'The Echoes of Jerash',
    category: 'History',
    place: 'Jerash',
    narrator: 'Abu Omar Al-Jerashi',
    narratorAvatarSeed: 'abu-omar-jerashi',
    duration: '18:42',
    excerpt:
      'Oral histories beneath the colonnades — whispers that still remain among a thousand columns.',
    imageSeed: 'jerash-columns-dusk',
    likes: 1200,
    comments: 84,
  },
  {
    id: 'echoes-of-petra',
    title: 'The Echoes of Petra',
    category: 'History',
    place: 'Petra',
    narrator: 'Abu Mahmoud',
    narratorAvatarSeed: 'abu-mahmoud',
    duration: '12:45',
    excerpt: 'A deep dive into the hidden chambers of the Treasury and the ones who carved them.',
    imageSeed: 'petra-treasury',
    likes: 1204,
    comments: 84,
  },
  {
    id: 'spice-market-tales',
    title: 'Tales from the Spice Market',
    category: 'Folklore',
    place: 'Amman',
    narrator: 'Sitti Fatima',
    narratorAvatarSeed: 'sitti-fatima',
    duration: '08:20',
    excerpt: 'Generational secrets of blending sumac and zaatar, told through the women who kept them.',
    imageSeed: 'spice-market',
    likes: 733,
    comments: 29,
  },
  {
    id: 'ceramic-legacy',
    title: 'The Ceramic Legacy',
    category: 'Personal',
    place: 'Jerash',
    narrator: 'Family of Sayegh',
    narratorAvatarSeed: 'sayegh',
    duration: '05:15',
    excerpt: 'The story of a family workshop in Jerash that has preserved a single kiln for four generations.',
    imageSeed: 'ceramic-workshop',
    likes: 410,
    comments: 12,
  },
]

export const mapPins: MapPin[] = [
  { id: 'p1', storyId: 'spice-market-tales', lat: 31.9539, lng: 35.9106, kind: 'dense', x: 47, y: 40 },
  { id: 'p2', storyId: 'ceramic-legacy', lat: 32.2745, lng: 35.8912, kind: 'recent', x: 47, y: 46 },
  { id: 'p3', storyId: 'echoes-of-petra', lat: 30.3285, lng: 35.4444, kind: 'featured', x: 40, y: 68 },
  { id: 'p4', storyId: 'echoes-of-jerash', lat: 32.2808, lng: 35.8993, kind: 'featured', x: 48, y: 36 },
  { id: 'p5', storyId: 'loom-of-ancestors', lat: 31.716, lng: 35.7939, kind: 'dense', x: 45, y: 44 },
  { id: 'p6', storyId: 'morning-steam', lat: 31.9497, lng: 35.9328, kind: 'recent', x: 48, y: 41 },
  { id: 'p7', storyId: 'echoes-red-desert', lat: 29.5766, lng: 35.419, kind: 'featured', x: 42, y: 78 },
]

export const transcript: TranscriptLine[] = [
  { time: '00:00', text: '[Soft wind blowing over stone ruins, traditional Oud melody starts]' },
  { time: '00:12', text: 'Welcome to Jerash, the city of a thousand columns. My grandfather used to say that every stone here has a memory, if you listen closely enough.' },
  { time: '00:45', text: 'I remember when I was a young boy, we would walk through the Oval Plaza before the sun reached its peak. The shadows of the columns would stretch like giant fingers across the limestone.', highlighted: true },
  { time: '01:22', text: 'People think of these as just ruins, but for us, they were our playground, our classroom, and our connection to the titans of the past.' },
]

export const upNext = [
  { id: 'weavers-song', title: "The Weaver's Song", author: 'Salma Khalil', duration: '12:05', imageSeed: 'madaba-loom' },
  { id: 'steam-al-balad', title: 'Steam of the Al-Balad', author: 'Omar S.', duration: '15:30', imageSeed: 'balad-market' },
]

export const reflections: Comment[] = [
  { name: 'Mariam F.', avatarSeed: 'mariam-f', timeAgo: '2 days ago', text: 'This brought back so many memories of our school trips to Jerash. Hearing the acoustics described really transported me back to the stage.', likes: 12 },
  { name: 'Khalid J.', avatarSeed: 'khalid-j', timeAgo: '2 days ago', text: 'The detail about the Cardo grooves is fascinating. Oral heritage like this is why I love this platform.', likes: 24 },
  { name: 'Sarah T.', avatarSeed: 'sarah-t', timeAgo: '2 days ago', text: 'Absolutely mesmerizing narration. Abu Omar has a voice made for history.', likes: 8 },
]

export const feedPosts: FeedPost[] = [
  {
    id: 'mosaic-restoration',
    name: 'Layla Al-Sayed',
    place: 'Madaba, Jordan',
    avatarSeed: 'layla-al-sayed',
    imageSeed: 'mosaic-workshop',
    likes: 1242,
    comments: 48,
    caption: 'Preserving the geometry of the past. Today we are restoring a 6th-century floor pattern. Every small stone tells a piece of our collective hikaya. #Heritage #Madaba #Mosaics',
    timeAgo: '2 hours ago',
  },
  {
    id: 'oval-plaza-goldenhour',
    name: 'Omar Kassab',
    place: 'Jerash, Jordan',
    avatarSeed: 'omar-kassab',
    imageSeed: 'jerash-oval-plaza',
    likes: 890,
    comments: 32,
    caption: "Golden hour at the Oval Plaza. It's hard to imagine that thousands of years ago, people walked these same stones, sharing their own stories under this same sun. #History #Jerash #Jordan",
    timeAgo: '5 hours ago',
    liked: true,
  },
]

export const places = [
  { name: 'Petra', person: 'Amira', seed: 'amira' },
  { name: 'Amman', person: 'Abu', seed: 'abu' },
  { name: 'Madaba', person: 'Layla', seed: 'layla' },
  { name: 'Jerash', person: 'Omar', seed: 'omar' },
  { name: 'Wadi Rum', person: 'Zaid', seed: 'zaid' },
  { name: 'Aqaba', person: 'Farah', seed: 'farah' },
]

export const suggestedStorytellers = [
  { name: 'Yousef Hadid', handle: '@yousef_h', seed: 'yousef-hadid' },
  { name: 'Nadia Faris', handle: '@nadia_f', seed: 'nadia-faris' },
  { name: 'Khalid Mansour', handle: '@khalid_m', seed: 'khalid-mansour' },
]

export const visitPlan = [
  { title: 'The Treasury, Petra', date: 'Oct 24, 2024', who: 'Abu Ahmad' },
  { title: 'Amman Citadel', date: 'Oct 26, 2024', who: 'Salma K.' },
]

export { imageUrl, avatarUrl, placeCircleImage } from './images'
