import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import VideoConsole from './VideoConsole'

type Call = { url: string; method: string; body: Record<string, unknown> | null }

function stubApi(jobs: unknown[] = []) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
      calls.push({ url, method, body })
      if (url.endsWith('/staff/videos/config'))
        return Promise.resolve(
          Response.json({
            enabled: true,
            default_provider: 'gemini_omni',
            narrated_max_seconds: 60,
            providers: [
              {
                id: 'gemini_omni',
                label: 'Gemini Omni Flash (AI Studio key)',
                models: ['gemini-omni-1.2-flash'],
                available: true,
                reason: '',
                supports_seed: false,
                max_shot_seconds: 15,
              },
              {
                id: 'fal',
                label: 'fal.ai',
                models: ['fal-ai/wan/v2.2-a14b/image-to-video'],
                available: true,
                reason: '',
              },
            ],
          }),
        )
      if (url.includes('/stories?'))
        return Promise.resolve(
          Response.json({ items: [{ id: 'story-1', title: 'Petra at dawn' }], next_cursor: null }),
        )
      if (url.endsWith('/staff/videos/plan'))
        return Promise.resolve(
          Response.json({
            shots: [
              { start_ms: 0, end_ms: 14300, seconds: 15, lines: 4 },
              { start_ms: 14300, end_ms: 59300, seconds: 15, lines: 10 },
            ],
            seconds: 59.3,
            estimate_usd: '4.80',
            lines: 14,
            lines_total: 15,
          }),
        )
      if (url.endsWith('/retry')) return Promise.resolve(Response.json({}, { status: 202 }))
      if (url.endsWith('/staff/videos') && method === 'POST')
        return Promise.resolve(Response.json({}, { status: 202 }))
      return Promise.resolve(Response.json(jobs))
    }),
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

it('shows the shots and cost of a narrated video before queuing it', async () => {
  const calls = stubApi()
  render(<VideoConsole />)
  await screen.findByRole('option', { name: 'Petra at dawn' })
  fireEvent.change(screen.getByLabelText('Story'), { target: { value: 'story-1' } })
  fireEvent.change(screen.getByLabelText('Video type'), { target: { value: 'narrated' } })
  expect(
    await screen.findByText(
      'Shots: 2 · Length: 0:59 · Lines covered: 14 of 15 · About 4.80 USD reserved',
    ),
  ).toBeInTheDocument()
  const plan = calls.find((call) => call.url.endsWith('/plan'))
  expect(plan?.body).toMatchObject({
    story_id: 'story-1',
    provider: 'gemini_omni',
    mode: 'narrated',
    soundtrack: 'narration',
    subtitles: true,
  })

  fireEvent.change(screen.getByLabelText('Soundtrack'), { target: { value: 'recording' } })
  fireEvent.click(screen.getByLabelText('Burn in subtitles'))
  const submit = screen.getByRole('button', { name: 'Generate narrated video' })
  await vi.waitFor(() => expect(submit).toBeEnabled())
  fireEvent.click(submit)
  await vi.waitFor(() =>
    expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/staff/videos'))).toBe(
      true,
    ),
  )
  const queued = calls.find((call) => call.method === 'POST' && call.url.endsWith('/staff/videos'))
  expect(queued?.body).toMatchObject({
    mode: 'narrated',
    soundtrack: 'recording',
    subtitles: false,
  })
})

it('offers narrated videos only for providers that make shots of a chosen length', async () => {
  stubApi()
  render(<VideoConsole />)
  await screen.findByRole('option', { name: 'fal.ai' })
  fireEvent.change(screen.getByLabelText('Video provider'), { target: { value: 'fal' } })
  expect(
    screen.getByText('Narrated videos need Gemini Omni Flash or the offline demo.'),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('option', { name: 'Narrated video (story soundtrack, up to 60 s)' }),
  ).toBeDisabled()
})

it('retries a failed narrated video from its failed shot', async () => {
  const calls = stubApi([
    {
      id: 'video-1',
      story_id: 'story-1',
      provider: 'gemini_omni',
      model: 'gemini-omni-1.2-flash',
      prompt: 'Shot 1 of 4',
      status: 'failed',
      progress: 'Shot 2 of 4: failed',
      error: 'Gemini Omni could not generate this video.',
      demo: false,
      video_url: null,
      mode: 'narrated',
      shots: 4,
      seconds: 59.3,
      retryable: true,
    },
  ])
  render(<VideoConsole />)
  expect(await screen.findByText('Narrated video · Shots: 4 · Length: 0:59')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry from the failed shot' }))
  await vi.waitFor(() =>
    expect(
      calls.some((call) => call.method === 'POST' && call.url.endsWith('/video-1/retry')),
    ).toBe(true),
  )
})
