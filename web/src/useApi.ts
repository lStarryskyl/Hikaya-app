import { useEffect, useState } from 'react'
import { ApiError } from './api'

/** Load once per change of `deps`. Ignores results that arrive after the component moved on. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({
    data: null,
    error: '',
    loading: true,
  })
  useEffect(() => {
    let current = true
    setState((s) => ({ ...s, loading: true, error: '' }))
    // Promise.resolve().then also turns a load that throws at once into a handled error.
    Promise.resolve()
      .then(load)
      .then((data) => current && setState({ data, error: '', loading: false }))
      .catch(
        (e) =>
          current &&
          setState({
            data: null,
            error: e instanceof ApiError ? e.message : 'Could not load this. Please try again.',
            loading: false,
          }),
      )
    return () => {
      current = false
    }
  }, deps)
  return state
}
