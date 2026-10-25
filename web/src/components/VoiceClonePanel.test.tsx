import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import VoiceClonePanel from './VoiceClonePanel'

afterEach(() => vi.unstubAllGlobals())
it('requires every consent acknowledgment before exposing recording controls', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        Response.json(
          url.endsWith('/consent')
            ? {
                version: 'v1',
                text: 'Explicit voice consent',
                text_ar: 'موافقة',
                min_seconds: 30,
                max_seconds: 60,
              }
            : [],
        ),
      ),
    ),
  )
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
  }
  render(<VoiceClonePanel />)
  const create = await screen.findByRole('button', { name: 'Create a voice clone' })
  await vi.waitFor(() => expect(create).toBeEnabled())
  fireEvent.click(create)
  expect(screen.getByRole('dialog')).toHaveTextContent('Explicit voice consent')
  expect(screen.queryByLabelText('Start recording')).not.toBeInTheDocument()
  for (const label of [
    'I am the speaker in this sample.',
    'I control the rights to this voice.',
    'I consent to storage, provider processing, and synthetic heritage narration.',
  ])
    fireEvent.click(screen.getByLabelText(label))
  expect(screen.getByLabelText('Start recording')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Consent and create clone' })).toBeDisabled()
})
