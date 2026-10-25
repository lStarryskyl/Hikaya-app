import { api } from './api'
export interface Checkout {
  id: string
  status: 'processing' | 'succeeded' | 'failed'
  sandbox: true
  message: string
}
export interface VideoSample {
  id: string
  title: string
  description: string
  credit: string
  source_url: string
  video_url: string
  poster_url: string
  duration_seconds: number
}
export const getPlans = () =>
  api<{ features: { id: string; label: string; free: boolean; premium: boolean }[] }>('/plans')
export const getSamples = () => api<VideoSample[]>('/video-samples')
export const startCheckout = (requestId: string, scenario: 'success' | 'failure') =>
  api<Checkout>('/billing/checkout', { body: { request_id: requestId, scenario } })
export const getCheckout = (id: string) => api<Checkout>(`/billing/checkout/${id}`)
