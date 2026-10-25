import { useEffect, useRef, useState } from 'react'
import { ApiError } from './api'
import { getFeed, getPins, type DiscoveryFilters, type FeedPage, type Pin } from './discover'

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function useNearby() {
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  useEffect(
    () => () => {
      generation.current++
    },
    [],
  )
  function clear() {
    generation.current++
    setPosition(null)
    setLoading(false)
    setError('')
  }
  function request() {
    const current = ++generation.current
    setError('')
    if (!navigator.geolocation) {
      setError('Location is unavailable in this browser. Search by place instead.')
      return
    }
    setLoading(true)
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (generation.current !== current) return
        setPosition({ latitude: coords.latitude, longitude: coords.longitude })
        setLoading(false)
      },
      (failure) => {
        if (generation.current !== current) return
        setPosition(null)
        setLoading(false)
        setError(
          failure.code === 1
            ? 'Location access was denied. Search by place, or allow location in your browser settings.'
            : failure.code === 3
              ? 'Location took too long. Try again or search by place.'
              : 'Your location could not be found. Try again or search by place.',
        )
      },
      { timeout: 10000, maximumAge: 60000, enableHighAccuracy: false },
    )
  }
  return { position, loading, error, request, clear }
}

export function useDiscovery(filters: DiscoveryFilters) {
  const key = JSON.stringify(filters)
  const [revision, setRevision] = useState(0)
  const generation = useRef(0)
  const morePending = useRef(false)
  const [state, setState] = useState<{
    key: string
    page: FeedPage | null
    pins: Pin[]
    loading: boolean
    error: string
  }>({ key, page: null, pins: [], loading: true, error: '' })
  useEffect(() => {
    const current = ++generation.current
    morePending.current = false
    const snapshot = JSON.parse(key) as DiscoveryFilters
    setState({ key, page: null, pins: [], loading: true, error: '' })
    Promise.all([getFeed(snapshot), getPins(snapshot)])
      .then(([page, pins]) => {
        if (current === generation.current) setState({ key, page, pins, loading: false, error: '' })
      })
      .catch((e: unknown) => {
        if (current === generation.current)
          setState({
            key,
            page: null,
            pins: [],
            loading: false,
            error: e instanceof ApiError ? e.message : 'Could not load stories. Please try again.',
          })
      })
    return () => {
      generation.current++
    }
  }, [key, revision])
  async function loadMore() {
    if (morePending.current || !state.page?.next_cursor || state.key !== key) return
    const current = generation.current
    morePending.current = true
    setState((s) => ({ ...s, loading: true, error: '' }))
    try {
      const page = await getFeed({ ...filters, cursor: state.page.next_cursor })
      if (current === generation.current)
        setState((s) => ({
          ...s,
          loading: false,
          page: {
            ...page,
            items: [
              ...(s.page?.items ?? []),
              ...page.items.filter((i) => !s.page?.items.some((p) => p.id === i.id)),
            ],
          },
        }))
    } catch (e) {
      if (current === generation.current)
        setState((s) => ({
          ...s,
          loading: false,
          error: e instanceof ApiError ? e.message : 'Could not load more stories.',
        }))
    } finally {
      if (current === generation.current) morePending.current = false
    }
  }
  return {
    ...(state.key === key ? state : { page: null, pins: [], loading: true, error: '' }),
    loadMore,
    retry: () => setRevision((r) => r + 1),
  }
}
