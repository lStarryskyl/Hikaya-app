import { api } from './api'
import type { StoryCard } from './discover'
import type { StoryRecord } from './stories'

/** A held story, with everything a reviewer needs to judge it. */
export interface HeldStory extends StoryRecord {
  /** The reviewer wrote it, so another member of staff must decide. */
  own: boolean
}

export interface Candidate extends StoryCard {
  own: boolean
}

export interface ReviewPage {
  held: HeldStory[]
  candidates: Candidate[]
  museum: Candidate[]
}

export interface ActionResult {
  id: string
  status: string
  curated: boolean
}

export type AuditActionName = 'approve' | 'reject' | 'curate' | 'dismiss' | 'uncurate'

export interface AuditEntry {
  id: string
  action: AuditActionName
  actor: { id: string; display_name: string } | null
  target: { type: string; id: string; title: string | null }
  detail: { note?: string } | null
  at: string
}

export interface SpendSummary {
  total_usd: string
  /** Today on the card budget, which is what the daily cap counts. */
  today_card_usd: string
  card_usd: string
  azure_usd: string
  by_provider: { provider: string; usd: string }[]
  card_cap_usd: string
  daily_cap_usd: string
  azure_cap_usd: string
}

export const AUDIT_LABELS: Record<AuditActionName, string> = {
  approve: 'published a held story',
  reject: 'sent a story back',
  curate: 'added a story to the museum',
  dismiss: 'set a candidate aside',
  uncurate: 'removed a story from the museum',
}

const story = (id: string, action: string) => `/staff/stories/${id}/${action}`

export const getReviewPage = () => api<ReviewPage>('/staff/review')
export const approveStory = (id: string) =>
  api<ActionResult>(story(id, 'approve'), { method: 'POST' })
export const rejectStory = (id: string, note: string) =>
  api<ActionResult>(story(id, 'reject'), { method: 'POST', body: { note: note.trim() || null } })
export const curateStory = (id: string) =>
  api<ActionResult>(story(id, 'curate'), { method: 'POST' })
export const dismissCandidate = (id: string) =>
  api<ActionResult>(story(id, 'dismiss'), { method: 'POST' })
export const uncurateStory = (id: string) =>
  api<ActionResult>(story(id, 'curation'), { method: 'DELETE' })
export const getAuditLog = () => api<AuditEntry[]>('/staff/audit')
export const getSpend = () => api<SpendSummary>('/staff/spend')

export const isStaff = (role: string | undefined) => role === 'reviewer' || role === 'admin'
