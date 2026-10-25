import { useSyncExternalStore } from 'react'
import english from './locales/en.json'
import arabic from './locales/ar.json'
import sources from './locales/keys.json'

export type Locale = 'en' | 'ar'
const listeners = new Set<() => void>()
let locale: Locale = 'en'
try {
  locale = localStorage.getItem('hikaya.locale') === 'ar' ? 'ar' : 'en'
} catch {
  /* Storage can be disabled. */
}
function applyDirection() {
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
}
applyDirection()
export function setLocale(next: Locale) {
  locale = next
  applyDirection()
  try {
    localStorage.setItem('hikaya.locale', next)
  } catch {
    /* Keep the session preference. */
  }
  listeners.forEach((notify) => notify())
}
export function useLocale() {
  return useSyncExternalStore(
    (notify) => {
      listeners.add(notify)
      return () => {
        listeners.delete(notify)
      }
    },
    () => locale,
  )
}
/** Translate interface copy only. Story text and names are never passed here. */
export function t<T>(source: T): T {
  if (typeof source !== 'string') return source
  const key = (sources as Record<string, string>)[source] ?? source
  return (((locale === 'ar' ? arabic : english) as Record<string, string>)[key] as T) ?? source
}
export function number(value: number, options?: Intl.NumberFormatOptions) {
  return new Intl.NumberFormat(locale === 'ar' ? 'ar-JO' : 'en', options).format(value)
}
export function currentLocale() {
  return locale === 'ar' ? 'ar-JO' : 'en'
}

export function message(source: string, values: Record<string, string | number>): string {
  return t(source).replace(/\{(\w+)\}/g, (placeholder, key: string) =>
    String(values[key] ?? placeholder),
  )
}
