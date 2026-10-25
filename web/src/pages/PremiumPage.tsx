import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { captions } from '../captions'
import { t, useLocale } from '../i18n'
import { getCheckout, getPlans, getSamples, startCheckout, type VideoSample } from '../premium'
import { isStaff } from '../staff'
import { useApi } from '../useApi'

export default function PremiumPage() {
  useLocale()
  const { user, refreshUser } = useAuth()
  const plans = useApi(getPlans, [])
  const samples = useApi(getSamples, [])
  const [params, setParams] = useSearchParams()
  const checkoutId = params.get('checkout')
  const [revision, setRevision] = useState(0)
  const checkout = useApi(
    () => (checkoutId && user ? getCheckout(checkoutId) : Promise.resolve(null)),
    [checkoutId, user?.id, revision],
  )
  const [scenario, setScenario] = useState<'success' | 'failure'>('success')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(crypto.randomUUID())
  const refreshed = useRef('')
  const premium = user?.plan === 'premium' || isStaff(user?.role)
  const processing = starting || checkout.data?.status === 'processing'
  useEffect(() => {
    if (checkout.data?.status !== 'processing') return
    const timer = window.setTimeout(() => setRevision((r) => r + 1), 800)
    return () => window.clearTimeout(timer)
  }, [checkout.data])
  useEffect(() => {
    if (checkout.data?.status === 'succeeded' && refreshed.current !== checkout.data.id) {
      refreshed.current = checkout.data.id
      void refreshUser().catch(() => {
        refreshed.current = ''
        setError(t('Could not refresh membership. Reload the page.'))
      })
    }
    if (checkout.data?.status === 'succeeded' || checkout.data?.status === 'failed')
      requestId.current = crypto.randomUUID()
  }, [checkout.data, refreshUser])
  async function begin() {
    if (processing) return
    setStarting(true)
    setError('')
    try {
      const attempt = await startCheckout(requestId.current, scenario)
      setParams({ checkout: attempt.id })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Checkout could not start. Try again.'))
    } finally {
      setStarting(false)
    }
  }
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6">
      <header>
        <h1 className="font-serif text-3xl">{t('Hikaya Premium')}</h1>
        <p className="mt-2 text-muted2">{t('More ways to bring heritage stories to life.')}</p>
        <p className="mt-3 rounded-lg bg-gold-light p-3 text-sm text-gold">
          {t('Sandbox demo: no card details, no real charge, no recurring subscription.')}
        </p>
      </header>
      <section aria-labelledby="plan-heading">
        <h2 id="plan-heading" className="mb-3 font-serif text-xl">
          {t('Compare plans')}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-start text-sm">
            <thead>
              <tr>
                <th scope="col" className="p-3 text-start">
                  {t('Feature')}
                </th>
                <th scope="col" className="p-3">
                  {t('Free')}
                </th>
                <th scope="col" className="p-3">
                  {t('Premium')}
                </th>
              </tr>
            </thead>
            <tbody>
              {plans.data?.features.map((feature) => (
                <tr key={feature.id} className="border-t border-border">
                  <th scope="row" className="p-3 text-start font-normal">
                    {t(feature.label)}
                  </th>
                  <td className="p-3 text-center">
                    {t(feature.free ? 'Included' : 'Not included')}
                  </td>
                  <td className="p-3 text-center">
                    {t(feature.premium ? 'Included' : 'Not included')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {plans.error && <p role="alert">{t(plans.error)}</p>}
      </section>
      <section
        className="rounded-xl2 border border-border bg-panel p-5"
        aria-labelledby="checkout-heading"
      >
        <h2 id="checkout-heading" className="font-serif text-xl">
          {t('Demo checkout')}
        </h2>
        {user ? (
          <>
            <p className="my-3">
              {t(
                user.plan === 'premium'
                  ? 'Your Premium membership is active.'
                  : 'Your current plan is Free.',
              )}
            </p>
            <label className="block text-sm">
              {t('Simulate payment result')}
              <select
                value={scenario}
                disabled={processing}
                onChange={(e) => {
                  setScenario(e.target.value as 'success' | 'failure')
                  requestId.current = crypto.randomUUID()
                }}
                className="ms-2 rounded-lg border border-border p-2"
              >
                <option value="success">{t('Success')}</option>
                <option value="failure">{t('Failure')}</option>
              </select>
            </label>
            <button
              type="button"
              disabled={processing || user.plan === 'premium'}
              onClick={() => void begin()}
              className="mt-4 rounded-full bg-terracotta px-4 py-2 text-cream disabled:opacity-50"
            >
              {t(processing ? 'Processing demo payment…' : 'Complete dummy checkout')}
            </button>
          </>
        ) : (
          <Link
            to="/signin?next=%2Fpremium"
            className="mt-3 inline-block text-terracotta-dark underline"
          >
            {t('Sign in to try Premium')}
          </Link>
        )}
        {checkout.data && (
          <p role="status" className="mt-3">
            {t(
              checkout.data.status === 'processing'
                ? 'Processing demo payment…'
                : checkout.data.status === 'succeeded'
                  ? 'Demo payment succeeded. Premium unlocked.'
                  : 'Demo payment failed. Your plan has not changed. Try again.',
            )}
          </p>
        )}
        {(error || checkout.error) && (
          <div role="alert" className="mt-3 text-terracotta-dark">
            <p>{t(error || checkout.error)}</p>
            <button type="button" onClick={() => setRevision((r) => r + 1)} className="underline">
              {t('Try again')}
            </button>
          </div>
        )}
      </section>
      <section aria-labelledby="samples-heading">
        <h2 id="samples-heading" className="font-serif text-xl">
          {t('AI video samples')}
        </h2>
        <p className="my-3 text-sm text-muted2">
          {t(
            'Official Wan 2.2 demonstration excerpts. These are provider examples, not videos of Hikaya stories.',
          )}
        </p>
        {!premium && (
          <p className="mb-4 rounded-lg bg-terracotta-light p-3 text-sm">
            {t('Premium unlocks sample playback. Complete the dummy checkout above.')}
          </p>
        )}
        {samples.error && <p role="alert">{t(samples.error)}</p>}
        <div className="grid gap-5 md:grid-cols-2">
          {samples.data?.map((sample) => (
            <figure
              key={sample.id}
              className="overflow-hidden rounded-xl2 border border-border bg-panel"
            >
              {premium ? (
                <SamplePlayer sample={sample} />
              ) : (
                <img
                  src={sample.poster_url}
                  alt={t(sample.title)}
                  loading="lazy"
                  className="aspect-video w-full object-cover"
                />
              )}
              <figcaption className="p-4">
                <h3 className="font-medium">{t(sample.title)}</h3>
                <p className="my-2 text-sm text-muted2">{t(sample.description)}</p>
                <a
                  href={sample.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-terracotta-dark underline"
                >
                  {sample.credit}
                </a>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>
    </div>
  )
}

function SamplePlayer({ sample }: { sample: VideoSample }) {
  useLocale()
  const [failed, setFailed] = useState(false)
  return (
    <div>
      <video
        controls
        muted
        playsInline
        preload="none"
        poster={sample.poster_url}
        src={sample.video_url}
        aria-label={t(sample.title)}
        className="aspect-video w-full bg-black"
        onError={() => setFailed(true)}
      >
        <track
          kind="descriptions"
          srcLang="en"
          label="Description"
          src={captions([{ start_ms: 0, end_ms: 6000, text: sample.description }])}
        />
      </video>
      {failed && (
        <p role="alert" className="p-3 text-sm text-terracotta-dark">
          {t('This sample is unavailable. Try again later.')}
        </p>
      )}
    </div>
  )
}
