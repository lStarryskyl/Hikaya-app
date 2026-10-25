import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDebounced, useDiscovery, useNearby } from './useDiscovery'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('discovery interactions', () => {
  it('debounces typing and cancels older timers', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ value }) => useDebounced(value), {
      initialProps: { value: '' },
    })
    rerender({ value: 'pet' })
    act(() => {
      vi.advanceTimersByTime(200)
    })
    rerender({ value: 'petra' })
    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(result.current).toBe('')
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe('petra')
  })
  it('requests location only on activation and explains denial', () => {
    const getCurrentPosition = vi.fn((_success, failure) => failure({ code: 1 }))
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
    const { result } = renderHook(useNearby)
    expect(getCurrentPosition).not.toHaveBeenCalled()
    act(() => result.current.request())
    expect(result.current.position).toBeNull()
    expect(result.current.error).toContain('denied')
    expect(result.current.loading).toBe(false)
  })
  it('ignores a location response after nearby mode is cancelled', () => {
    let resolve: (value: { coords: { latitude: number; longitude: number } }) => void = () => {}
    vi.stubGlobal('navigator', {
      geolocation: {
        getCurrentPosition: vi.fn((success) => {
          resolve = success
        }),
      },
    })
    const { result } = renderHook(useNearby)
    act(() => result.current.request())
    act(() => result.current.clear())
    act(() => resolve({ coords: { latitude: 31, longitude: 35 } }))
    expect(result.current.position).toBeNull()
  })
  it('keeps results from an old query from replacing a newer search', async () => {
    let resolveOld: (value: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/map/pins')) return Promise.resolve(Response.json([]))
        if (url.includes('q=old'))
          return new Promise<Response>((resolve) => {
            resolveOld = resolve
          })
        return Promise.resolve(Response.json({ items: [], total: 7, next_cursor: null }))
      }),
    )
    const { result, rerender } = renderHook(({ q }) => useDiscovery({ q }), {
      initialProps: { q: 'old' },
    })
    rerender({ q: 'new' })
    await waitFor(() => expect(result.current.page?.total).toBe(7))
    await act(async () => resolveOld(Response.json({ items: [], total: 99, next_cursor: null })))
    expect(result.current.page?.total).toBe(7)
  })
})
