import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import TranscriptEditor from '../components/TranscriptEditor'
import CreateStoryPage from './CreateStoryPage'

type Call = { url: string; method: string; body: unknown }

const LIMITS = {
  audio_max_mb: 100,
  audio_max_minutes: 60,
  photo_types: ['image/png'],
  photo_max_mb: 15,
  photos_per_story: 12,
  text_max_chars: 20000,
}

function story(overrides: Record<string, unknown> = {}) {
  return {
    tags: [],
    id: 'story-1',
    title: '',
    category: null,
    place_name: '',
    latitude: null,
    longitude: null,
    original_language: 'english',
    duration_ms: null,
    status: 'draft',
    published_at: null,
    created_at: '2026-11-12T00:00:00Z',
    author: { id: 'member', display_name: 'Member' },
    audio: null,
    layers: [],
    place_slug: null,
    cover: null,
    curated: false,
    photos: [],
    consent: null,
    narration_source: 'polished',
    narration: null,
    slideshow: null,
    moderation: null,
    review: null,
    ...overrides,
  }
}

const WRITTEN = story({
  layers: [
    {
      kind: 'verbatim',
      language: 'english',
      edited: false,
      segments: [
        { start_ms: 0, end_ms: 1867, text: 'My grandfather told stories.' },
        { start_ms: 1867, end_ms: 3367, text: 'We listened.' },
      ],
    },
  ],
})

function stubApi() {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const body = init?.body && typeof init.body === 'string' ? JSON.parse(init.body) : null
      calls.push({ url, method, body })
      if (url.endsWith('/auth/me'))
        return Promise.resolve(
          Response.json({ id: 'member', role: 'member', display_name: 'Member', plan: 'free' }),
        )
      if (url.endsWith('/stories/limits')) return Promise.resolve(Response.json(LIMITS))
      if (url.endsWith('/stories/consent'))
        return Promise.resolve(Response.json({ version: 'v1', text: 'I agree.' }))
      if (url.endsWith('/places')) return Promise.resolve(Response.json([]))
      if (url.endsWith('/stories') && method === 'POST')
        return Promise.resolve(Response.json(story(), { status: 201 }))
      if (url.endsWith('/stories/story-1/text')) return Promise.resolve(Response.json(WRITTEN))
      return Promise.resolve(Response.json({}))
    }),
  )
  return calls
}

function renderPage() {
  render(
    <MemoryRouter
      initialEntries={['/create']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <CreateStoryPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

it('saves a written story as its text and lets the member continue', async () => {
  const calls = stubApi()
  renderPage()
  const box = await screen.findByLabelText('Write or paste your story')
  expect(box).toBeDisabled() // the language comes first
  expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()

  fireEvent.change(screen.getByLabelText('Language of the story'), {
    target: { value: 'english' },
  })
  const words = 'My grandfather told stories. We listened.'
  fireEvent.change(box, { target: { value: words } })
  expect(await screen.findByText(`${words.length} of 20,000 characters`)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Use this text' }))

  expect(await screen.findByText('Text saved · 2 lines')).toBeInTheDocument()
  const saved = calls.find((c) => c.url.endsWith('/stories/story-1/text'))
  expect(saved).toMatchObject({
    method: 'PUT',
    body: { text: 'My grandfather told stories. We listened.' },
  })
  expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  expect(screen.getByText('A recording replaces the text you saved.')).toBeInTheDocument()
})

it('loads a .txt file into the box so it can be read before it is used', async () => {
  const calls = stubApi()
  renderPage()
  fireEvent.change(await screen.findByLabelText('Language of the story'), {
    target: { value: 'english' },
  })
  const content = 'The well was ours.\nWe drew water at dawn.'
  const file = new File([content], 'story.txt', { type: 'text/plain' })
  // jsdom's File has no text(); every browser the page supports has it.
  Object.defineProperty(file, 'text', { value: () => Promise.resolve(content) })
  await act(async () => {
    fireEvent.change(screen.getByLabelText('Load a .txt file'), { target: { files: [file] } })
  })
  await waitFor(() =>
    expect(screen.getByLabelText('Write or paste your story')).toHaveValue(content),
  )
  // Nothing is saved until the member chooses to use it.
  expect(calls.some((c) => c.url.endsWith('/text'))).toBe(false)
})

it('numbers the lines of a story without a recording instead of showing times', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.endsWith('/pipeline'))
        return Promise.resolve(
          Response.json({
            steps: [{ step: 'polish', status: 'queued', message: 'Waiting to start.' }],
            complete: false,
          }),
        )
      return Promise.resolve(Response.json(WRITTEN))
    }),
  )
  render(<TranscriptEditor storyId="story-1" onStory={() => {}} />)
  expect(await screen.findByLabelText('Original words, line 2')).toHaveValue('We listened.')
  expect(screen.getByText('1')).toBeInTheDocument()
  expect(screen.getByText('2')).toBeInTheDocument()
  expect(screen.queryByText('0:01')).not.toBeInTheDocument()
})
