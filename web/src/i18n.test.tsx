import { act, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { message, setLocale, t, useLocale } from './i18n'
import en from './locales/en.json'
import ar from './locales/ar.json'

afterEach(() => act(() => setLocale('en')))
it('switches the interface direction while preserving the mounted input', () => {
  function Example() {
    useLocale()
    return (
      <>
        <h1>{t('Explore Jordan')}</h1>
        <input aria-label="draft" defaultValue="My unfinished story" />
      </>
    )
  }
  render(<Example />)
  const input = screen.getByLabelText('draft')
  act(() => setLocale('ar'))
  expect(screen.getByRole('heading')).toHaveTextContent('استكشف الأردن')
  expect(document.documentElement.dir).toBe('rtl')
  expect(document.documentElement.lang).toBe('ar')
  expect(screen.getByLabelText('draft')).toBe(input)
  expect(localStorage.getItem('hikaya.locale')).toBe('ar')
  act(() => setLocale('en'))
  expect(document.documentElement.dir).toBe('ltr')
})
it('has an Arabic translation for every English catalogue key and falls back for unknown copy', () => {
  expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
  setLocale('ar')
  expect(t('A new untranslated message')).toBe('A new untranslated message')
})
it('interpolates translated result counts', () => {
  setLocale('ar')
  expect(message('{count} stories found', { count: 7 })).toBe('عدد القصص: 7')
})
