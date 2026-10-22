import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api'

export type Role = 'member' | 'reviewer' | 'admin'

export interface User {
  id: string
  email: string
  display_name: string
  role: Role
}

interface AuthState {
  user: User | null
  /** True until the first check of "am I signed in?" has finished. */
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, displayName: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api<User>('/auth/me')
      .then((u) => !cancelled && setUser(u))
      .catch((e) => {
        // 401 just means "not signed in"; anything else also leaves the visitor signed out.
        if (!(e instanceof ApiError)) console.error(e)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    setUser(await api<User>('/auth/login', { body: { email, password } }))
  }, [])

  const signUp = useCallback(async (email: string, password: string, displayName: string) => {
    setUser(
      await api<User>('/auth/signup', {
        body: { email, password, display_name: displayName },
      }),
    )
  }, [])

  const signOut = useCallback(async () => {
    await api<void>('/auth/logout', { method: 'POST' })
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, signIn, signUp, signOut }),
    [user, loading, signIn, signUp, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]
  return letters.toUpperCase()
}
