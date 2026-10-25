import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import PremiumPage from './PremiumPage'
afterEach(() => vi.unstubAllGlobals())
it('refreshes membership from the server after a successful dummy checkout', async () => {
  let plan = 'free'
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.endsWith('/auth/me'))
        return Promise.resolve(
          Response.json({
            id: 'member',
            role: 'member',
            display_name: 'Member',
            email: 'test@example.com',
            plan,
          }),
        )
      if (url.endsWith('/plans')) return Promise.resolve(Response.json({ features: [] }))
      if (url.endsWith('/video-samples')) return Promise.resolve(Response.json([]))
      if (url.endsWith('/billing/checkout'))
        return Promise.resolve(
          Response.json({ id: 'attempt', status: 'processing', sandbox: true }),
        )
      plan = 'premium'
      return Promise.resolve(Response.json({ id: 'attempt', status: 'succeeded', sandbox: true }))
    }),
  )
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <PremiumPage />
      </AuthProvider>
    </MemoryRouter>,
  )
  await screen.findByText('Your current plan is Free.')
  fireEvent.click(screen.getByRole('button', { name: 'Complete dummy checkout' }))
  expect(await screen.findByText('Demo payment succeeded. Premium unlocked.')).toBeInTheDocument()
  expect(await screen.findByText('Your Premium membership is active.')).toBeInTheDocument()
  expect(
    screen.getByText('Sandbox demo: no card details, no real charge, no recurring subscription.'),
  ).toBeInTheDocument()
})
