import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import Avatar from './Avatar'
it('uses initials when the remote avatar fails and retries a changed source', () => {
  const { rerender } = render(<Avatar name="Um Ahmad" src="https://example.com/one.png" />)
  fireEvent.error(screen.getByRole('img'))
  expect(screen.getByRole('img', { name: 'Um Ahmad' })).toHaveTextContent('UA')
  rerender(<Avatar name="Um Ahmad" src="https://example.com/two.png" />)
  expect(screen.getByRole('img')).toHaveAttribute('src', 'https://example.com/two.png')
})
it('provides a stable fallback for an empty name', () => {
  render(<Avatar name="" />)
  expect(screen.getByRole('img')).toHaveTextContent('?')
})
