/**
 * MOCK ENGAGEMENT: browser-only demo content.
 *
 * Likes, comments, reflections, follows, the visit planner and notifications are mock in
 * this demo (see docs/DECISIONS.md, "Real and mock"). Nothing here is sent to or stored by
 * the server, and nothing here describes a real person. Real data comes from the API.
 */

function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/** Plausible, stable like and comment counts for a story. */
export function engagementFor(storyId: string): { likes: number; comments: number } {
  const h = hash(storyId)
  return { likes: 120 + (h % 1900), comments: 4 + ((h >>> 11) % 80) }
}

/** Placeholder avatars for invented people. Real accounts show initials instead. */
export function mockAvatarUrl(seed: string, size = 80): string {
  return `https://i.pravatar.cc/${size}?u=${encodeURIComponent(seed)}`
}

export const sampleReflections = [
  {
    name: 'Mariam F.',
    avatarSeed: 'mariam-f',
    timeAgo: '2 days ago',
    text: 'This brought back so many memories of school trips with my grandparents.',
    likes: 12,
  },
  {
    name: 'Khalid J.',
    avatarSeed: 'khalid-j',
    timeAgo: '2 days ago',
    text: 'Oral heritage like this is exactly why I love this platform.',
    likes: 24,
  },
  {
    name: 'Sarah T.',
    avatarSeed: 'sarah-t',
    timeAgo: '3 days ago',
    text: 'Absolutely mesmerising. I could listen to this voice for hours.',
    likes: 8,
  },
]

/** An example plan for the next two days, so the panel never shows stale dates. */
export function exampleVisitPlan(today = new Date()) {
  const day = (offset: number) => {
    const d = new Date(today)
    d.setDate(d.getDate() + offset)
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  }
  return [
    { title: 'The Treasury, Petra', date: day(1) },
    { title: 'Amman Citadel', date: day(2) },
  ]
}
