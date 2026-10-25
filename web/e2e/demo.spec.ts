import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import path from 'node:path'

// Maps have a local style in CI. No browser request can reach an AI provider or remote font.
test.beforeEach(async ({ page }) => {
  page.on('console', (message) => {
    if (message.type() === 'error' && message.text().includes('View failed:'))
      console.error(message.text())
  })
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') return route.continue()
    if (url.hostname === 'tiles.openfreemap.org')
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          version: 8,
          sources: {},
          layers: [
            { id: 'background', type: 'background', paint: { 'background-color': '#e7e0d3' } },
          ],
        }),
      })
    return route.abort('blockedbyclient')
  })
})

test('the complete member and staff demo path', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Every place has a voice/ })).toBeVisible()
  await page.getByRole('textbox', { name: 'Search stories', exact: true }).fill('Petra')
  await page.getByRole('textbox', { name: 'Search stories', exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Explore Jordan' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '1 stories found' })).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(1)
  await page.getByRole('button', { name: 'Clear filters' }).click()
  await page.getByRole('button', { name: 'Explore near me', exact: true }).click()
  await expect(page.getByLabel('Search radius')).toBeVisible()
  await expect(page.getByText(/Nearest first/)).toBeVisible()
  await page.getByRole('button', { name: 'Switch to Arabic' }).click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
  await expect(page.getByRole('heading', { name: 'استكشف الأردن' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('arabic-discovery.png'), fullPage: true })
  await page.getByRole('button', { name: 'التبديل إلى الإنجليزية' }).click()
  await page.getByRole('link', { name: 'Premium', exact: true }).click()
  await page.getByRole('link', { name: 'Sign in to try Premium' }).click()
  await page.getByRole('link', { name: 'Create an account', exact: true }).click()
  await page.getByLabel('Your name').fill('Demo Member')
  await page.getByLabel('Email', { exact: true }).fill(`demo-${Date.now()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('e2e-only-member-password')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Hikaya Premium' })).toBeVisible()
  await page.getByLabel('Simulate payment result').selectOption('failure')
  await page.getByRole('button', { name: 'Complete dummy checkout' }).click()
  await expect(
    page.getByText('Demo payment failed. Your plan has not changed. Try again.'),
  ).toBeVisible()
  expect((await (await page.request.get('/api/v1/auth/me')).json()).plan).toBe('free')
  await page.getByLabel('Simulate payment result').selectOption('success')
  await page.getByRole('button', { name: 'Complete dummy checkout' }).click()
  await expect(page.getByText('Your Premium membership is active.')).toBeVisible()
  await expect(page.locator('video')).toHaveCount(2)
  await page
    .locator('video')
    .first()
    .evaluate(async (element: HTMLVideoElement) => {
      await element.play()
      element.pause()
    })
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('link', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Email', { exact: true }).fill('staff-e2e@example.com')
  await page.getByLabel('Password', { exact: true }).fill('e2e-only-staff-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('link', { name: 'Staff Review', exact: true }).click()
  await page.getByRole('button', { name: 'Create a voice clone' }).click()
  const dialog = page.getByRole('dialog', { name: 'Voice consent' })
  await expect(dialog.getByLabel('Start recording')).toHaveCount(0)
  const speakerName = `Consenting demo speaker ${Date.now()}`
  await dialog.getByLabel('Speaker name').fill(speakerName)
  for (const label of [
    'I am the speaker in this sample.',
    'I control the rights to this voice.',
    'I consent to storage, provider processing, and synthetic heritage narration.',
  ])
    await dialog.getByLabel(label).check()
  await expect(dialog.getByLabel('Start recording')).toBeVisible()
  await dialog
    .getByLabel('Or upload a voice sample')
    .setInputFiles(path.resolve('e2e/fixtures/voice.wav'))
  await expect(dialog.getByRole('button', { name: 'Consent and create clone' })).toBeEnabled()
  await dialog.getByRole('button', { name: 'Consent and create clone' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page
      .getByRole('listitem')
      .filter({ hasText: speakerName })
      .getByText('Demo clone ready (no synthetic voice was created)', { exact: false }),
  ).toBeVisible()
  await page
    .getByRole('combobox', { name: 'Story', exact: true })
    .selectOption({ label: 'The Echoes of Petra' })
  await page.getByRole('combobox', { name: 'Video provider', exact: true }).selectOption('fake')
  const visualDirection = `A gentle camera move across the historic sandstone facade. Demo ${Date.now()}`
  await page.getByLabel('Visual direction').fill(visualDirection)
  await page.getByRole('button', { name: 'Generate video preview' }).click()
  const videoJob = page.getByRole('article').filter({ hasText: visualDirection })
  await expect(videoJob.getByLabel('Generated video preview')).toBeVisible()
  await videoJob
    .getByLabel('Generated video preview')
    .evaluate(async (element: HTMLVideoElement) => {
      await element.play()
      element.pause()
    })
  expect(
    (await (await page.request.get('/api/v1/staff/videos/config')).json()).providers.find(
      (p: { id: string }) => p.id === 'fal',
    ).available,
  ).toBe(false)
  const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  expect(audit.violations).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('staff-preview.png'), fullPage: true })
})

test('location denial preserves search and Arabic feed tabs are translated', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: (_success: unknown, failure: (error: { code: number }) => void) =>
          failure({ code: 1 }),
      },
    })
  })
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Explore near me', exact: true }).click()
  await expect(page.getByText(/Location access was denied/)).toBeVisible()
  await page.getByRole('textbox', { name: 'Filter stories' }).fill('Petra')
  await expect(page.getByRole('article')).toHaveCount(1)
  await page.getByRole('link', { name: 'Social Feed', exact: true }).click()
  await page.getByRole('button', { name: 'Switch to Arabic' }).click()
  await expect(page.getByRole('button', { name: 'لك', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'المتابَعون', exact: true })).toBeVisible()
  await page.setViewportSize({ width: 375, height: 812 })
  const width = await page.evaluate(() => document.documentElement.scrollWidth)
  if (width > 375)
    console.error(
      await page.evaluate(() =>
        Array.from(document.querySelectorAll('*'))
          .map((node) => ({
            tag: node.tagName,
            cls: node.className,
            width: node.getBoundingClientRect().width,
          }))
          .filter((node) => node.width > 375)
          .slice(0, 12),
      ),
    )
  expect(width).toBeLessThanOrEqual(375)
  const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  expect(audit.violations).toEqual([])
})

test('members cannot reach staff video or voice endpoints', async ({ page }) => {
  await page.goto('/')
  expect((await page.request.get('/api/v1/staff/videos/config')).status()).toBe(401)
  const signup = await page.request.post('/api/v1/auth/signup', {
    data: {
      email: `access-${Date.now()}@example.com`,
      password: 'e2e-only-member-password',
      display_name: 'Member',
      role: 'admin',
      plan: 'premium',
    },
  })
  expect(signup.status()).toBe(201)
  expect((await signup.json()).role).toBe('member')
  expect((await page.request.get('/api/v1/staff/videos/config')).status()).toBe(403)
  expect((await page.request.get('/api/v1/staff/voices')).status()).toBe(403)
  await page.goto('/staff')
  await expect(page.getByRole('heading', { name: 'Staff only' })).toBeVisible()
})
