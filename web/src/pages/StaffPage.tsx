import { captions } from '../captions'
import { t, useLocale, message } from '../i18n'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Landmark, ShieldAlert, Wallet, X } from 'lucide-react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Badge, Card, PillButton } from '../components/ui'
import Photo from '../components/Photo'
import {
  AUDIT_LABELS,
  approveStory,
  curateStory,
  dismissCandidate,
  getAuditLog,
  getReviewPage,
  getSpend,
  isStaff,
  rejectStory,
  uncurateStory,
  type Candidate,
  type HeldStory,
} from '../staff'
import {
  LANGUAGE_LABELS,
  LAYER_LABELS,
  MODERATION_LABELS,
  textDirection,
  textFont,
} from '../stories'
import { useApi } from '../useApi'

const VideoConsole = lazy(() => import('../components/VideoConsole'))
const VoiceClonePanel = lazy(() => import('../components/VoiceClonePanel'))

const OWN = 'Your own story: another member of staff must decide.'

/**
 * The staff page: held stories to publish or send back, museum candidates to curate or set
 * aside, and for admins the museum itself, the spend summary and the audit log.
 */
export default function StaffPage() {
  useLocale()

  const { user } = useAuth()
  const [round, setRound] = useState(0)
  const admin = user?.role === 'admin'
  const page = useApi(getReviewPage, [round])
  const audit = useApi(() => (admin ? getAuditLog() : Promise.resolve(null)), [round, admin])
  const spend = useApi(() => (admin ? getSpend() : Promise.resolve(null)), [round, admin])
  const [busy, setBusy] = useState<string | null>(null)
  // Buttons stay off until the lists have reloaded, so nobody acts on a row that has moved.
  const [error, setError] = useState('')

  if (!isStaff(user?.role)) {
    return (
      <div className="mx-auto max-w-md p-12 text-center">
        <h1 className="mb-2 font-serif text-2xl">{t('Staff only')}</h1>
        <p className="text-sm text-muted2">{t('This page is for reviewers and admins.')}</p>
      </div>
    )
  }

  /** Run one action on one story, then load everything again. */
  async function act(key: string, action: () => Promise<unknown>) {
    setBusy(key)
    setError('')
    try {
      await action()
      setRound((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('That did not work. Please try again.'))
    } finally {
      setBusy(null)
    }
  }

  const data = page.data
  const locked = busy !== null || page.loading
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6">
      <div>
        <h1 className="font-serif text-2xl">{t('Staff review')}</h1>
        <p className="text-sm text-muted">
          {t(
            'Stories held by the automatic check, and published stories that could join the museum.',
          )}
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-terracotta-light px-3 py-2 text-sm text-terracotta-dark"
        >
          {t(error)}
        </p>
      )}
      {page.error && <p className="text-sm text-terracotta-dark">{page.error}</p>}

      <Suspense fallback={<p role="status">{t('Loading…')}</p>}>
        <VideoConsole />
      </Suspense>
      <Suspense fallback={<p role="status">{t('Loading…')}</p>}>
        <VoiceClonePanel />
      </Suspense>
      <section aria-labelledby="held-heading">
        <h2 id="held-heading" className="mb-3 flex items-center gap-2 font-serif text-xl">
          <ShieldAlert size={18} className="text-terracotta" /> {t('Held stories')}
          {data && <span className="text-sm font-normal text-muted">({data.held.length})</span>}
        </h2>
        {data && data.held.length === 0 && <Empty>{t('Nothing is waiting for review.')}</Empty>}
        <div className="space-y-4">
          {data?.held.map((s) => (
            <HeldCard
              key={s.id}
              story={s}
              busy={busy === s.id}
              disabled={locked}
              onApprove={() => act(s.id, () => approveStory(s.id))}
              onReject={(note) => act(s.id, () => rejectStory(s.id, note))}
            />
          ))}
        </div>
      </section>

      <section aria-labelledby="candidates-heading">
        <h2 id="candidates-heading" className="mb-3 flex items-center gap-2 font-serif text-xl">
          <Landmark size={18} className="text-teal" /> {t('Museum candidates')}
          {data && (
            <span className="text-sm font-normal text-muted">({data.candidates.length})</span>
          )}
        </h2>
        {data && data.candidates.length === 0 && (
          <Empty>{t('No published stories are waiting for curation.')}</Empty>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.candidates.map((s) => (
            <StoryTile key={s.id} story={s}>
              {s.own ? (
                <p className="text-[11px] text-muted2">{t(OWN)}</p>
              ) : (
                <div className="flex gap-2">
                  <PillButton
                    type="button"
                    variant="teal"
                    className="!py-1.5 text-xs"
                    disabled={locked}
                    onClick={() => act(s.id, () => curateStory(s.id))}
                    aria-label={message('Add {title} to the museum', { title: s.title })}
                  >
                    <Check size={13} /> {t('Add to museum')}
                  </PillButton>
                  <PillButton
                    type="button"
                    variant="outline"
                    className="!py-1.5 text-xs"
                    disabled={locked}
                    onClick={() => act(s.id, () => dismissCandidate(s.id))}
                    aria-label={message('Not now: {title}', { title: s.title })}
                  >
                    <X size={13} /> {t('Not now')}
                  </PillButton>
                </div>
              )}
            </StoryTile>
          ))}
        </div>
      </section>

      <section aria-labelledby="museum-heading">
        <h2 id="museum-heading" className="mb-3 font-serif text-xl">
          {t('In the museum')}
          {data && <span className="text-sm font-normal text-muted">({data.museum.length})</span>}
        </h2>
        {data && data.museum.length === 0 && <Empty>{t('The museum is empty.')}</Empty>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.museum.map((s) => (
            <StoryTile key={s.id} story={s}>
              {admin &&
                (s.own ? (
                  <p className="text-[11px] text-muted2">{t(OWN)}</p>
                ) : (
                  <PillButton
                    type="button"
                    variant="outline"
                    className="!py-1.5 text-xs"
                    disabled={locked}
                    onClick={() => act(s.id, () => uncurateStory(s.id))}
                    aria-label={message('Remove {title} from the museum', { title: s.title })}
                  >
                    <X size={13} /> {t('Remove from museum')}
                  </PillButton>
                ))}
            </StoryTile>
          ))}
        </div>
      </section>

      {admin && spend.data && (
        <section aria-labelledby="spend-heading">
          <h2 id="spend-heading" className="mb-3 flex items-center gap-2 font-serif text-xl">
            <Wallet size={18} className="text-gold" /> {t('Spending on AI services')}
          </h2>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Total" value={`$${spend.data.total_usd}`} />
            <Stat
              label="Card, today"
              value={`$${spend.data.today_card_usd}`}
              note={message('daily limit ${limit}', { limit: spend.data.daily_cap_usd })}
            />
            <Stat
              label="Card"
              value={`$${spend.data.card_usd}`}
              note={message('limit ${limit}', { limit: spend.data.card_cap_usd })}
            />
            <Stat
              label="Azure grant"
              value={`$${spend.data.azure_usd}`}
              note={message('limit ${limit}', { limit: spend.data.azure_cap_usd })}
            />
          </div>
          <Card className="mt-3 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {t('By provider')}
            </div>
            {spend.data.by_provider.length === 0 ? (
              <p className="text-sm text-muted2">{t('Nothing has been spent yet.')}</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {spend.data.by_provider.map((p) => (
                    <tr key={p.provider} className="border-t border-border first:border-0">
                      <td className="py-1.5 capitalize">{p.provider}</td>
                      <td className="py-1.5 text-end font-mono">${p.usd}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>
      )}

      {admin && audit.data && (
        <section aria-labelledby="audit-heading">
          <h2 id="audit-heading" className="mb-3 font-serif text-xl">
            {t('Staff actions')}
          </h2>
          {audit.data.length === 0 ? (
            <Empty>{t('No staff actions yet.')}</Empty>
          ) : (
            <Card className="divide-y divide-border">
              {audit.data.map((e) => (
                <div
                  key={e.id}
                  className="flex flex-wrap items-baseline gap-x-2 px-4 py-2.5 text-sm"
                >
                  <time className="w-36 shrink-0 text-[11px] text-muted" dateTime={e.at}>
                    {new Date(e.at).toLocaleString()}
                  </time>
                  <span className="font-medium">
                    {e.actor?.display_name ?? t('A removed account')}
                  </span>
                  <span className="text-muted2">{t(AUDIT_LABELS[e.action])}:</span>
                  {e.target.title !== null ? (
                    <Link to={`/story/${e.target.id}`} className="text-terracotta hover:underline">
                      {e.target.title || 'Untitled story'}
                    </Link>
                  ) : (
                    <span className="italic text-muted">{t('a deleted story')}</span>
                  )}
                  {e.detail?.note && (
                    <q className="basis-full ps-36 text-[12px] italic text-muted2">
                      {e.detail.note}
                    </q>
                  )}
                </div>
              ))}
            </Card>
          )}
        </section>
      )}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  useLocale()

  return (
    <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted2">
      {t(children)}
    </p>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  useLocale()

  return (
    <Card className="p-4">
      <div className="text-[11px] uppercase tracking-wide text-muted">{t(label)}</div>
      <div className="font-serif text-2xl">{value}</div>
      {note && <div className="text-[11px] text-muted2">{note}</div>}
    </Card>
  )
}

function StoryTile({ story, children }: { story: Candidate; children: React.ReactNode }) {
  useLocale()

  return (
    <Card className="overflow-hidden">
      <Photo photo={story.cover} width={480} className="h-32 w-full object-cover" />
      <div className="space-y-2 p-3">
        <Link
          to={`/story/${story.id}`}
          className="block font-serif text-[15px] hover:text-terracotta"
        >
          {story.title || 'Untitled story'}
        </Link>
        <div className="text-[11px] text-muted">
          {story.author.display_name} · {story.place_name}
        </div>
        {story.excerpt && <p className="line-clamp-2 text-[12px] text-muted2">{story.excerpt}</p>}
        {t(children)}
      </div>
    </Card>
  )
}

function HeldCard({
  story,
  busy,
  disabled,
  onApprove,
  onReject,
}: {
  story: HeldStory
  busy: boolean
  disabled: boolean
  onApprove: () => void
  onReject: (note: string) => void
}) {
  useLocale()

  const [rejecting, setRejecting] = useState(false)
  const [note, setNote] = useState('')
  const raised = story.moderation?.labels.filter((l) => l.raised) ?? []
  // The text the check judged: the polished text, and the English translation of an Arabic story.
  const shown = story.layers.filter((l) => l.kind === 'polished' || l.kind === 'translation_en')

  return (
    <Card className="p-5">
      <article
        aria-label={message('Held story: {title}', { title: story.title || t('Untitled story') })}
      >
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link to={`/story/${story.id}`} className="font-serif text-lg hover:text-terracotta">
              {story.title || 'Untitled story'}
            </Link>
            <div className="text-[12px] text-muted">
              {story.author.display_name}
              {story.place_name && ` · ${story.place_name}`}
              {story.original_language && ` · ${LANGUAGE_LABELS[story.original_language]}`}
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {raised.map((l) => (
              <Badge key={l.label} tone="terracotta">
                {t(MODERATION_LABELS[l.label])}
              </Badge>
            ))}
          </div>
        </div>

        {raised.length > 0 && (
          <ul className="mb-3 list-disc space-y-0.5 ps-5 text-sm text-ink2">
            {raised.map((l) => (
              <li key={l.label}>
                <span className="font-medium">{t(MODERATION_LABELS[l.label])}:</span>{' '}
                {l.reason || 'No reason given.'}
              </li>
            ))}
          </ul>
        )}

        <div className="mb-3 grid gap-3 md:grid-cols-2">
          {shown.map((layer) => (
            <div key={layer.kind} className="rounded-lg bg-cream p-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
                {t(LAYER_LABELS[layer.kind])}
              </div>
              <p
                {...textDirection(layer.language)}
                className={`${textFont(layer.language)} text-sm leading-relaxed text-ink2`}
              >
                {layer.segments.map((s) => s.text).join(' ')}
              </p>
            </div>
          ))}
        </div>

        <div className="mb-4 flex flex-wrap gap-4">
          {story.audio && (
            <label className="text-[11px] text-muted">
              {t('Recording')}
              <audio
                aria-label={t('Recording')}
                controls
                preload="none"
                src={story.audio.url}
                className="mt-1 block h-9"
              >
                <track
                  kind="captions"
                  src={captions(story.layers.find((l) => l.kind === 'verbatim')?.segments)}
                  label={t('Transcript')}
                  srcLang={story.original_language === 'english' ? 'en' : 'ar'}
                />
              </audio>
            </label>
          )}
          {story.narration && (
            <label className="text-[11px] text-muted">
              {t('Narration')}
              <audio
                aria-label={t('Narration')}
                controls
                preload="none"
                src={story.narration.url}
                className="mt-1 block h-9"
              >
                <track
                  kind="captions"
                  src={captions(story.narration.segments)}
                  label={t('Transcript')}
                  srcLang={story.narration.language === 'english' ? 'en' : 'ar'}
                />
              </audio>
            </label>
          )}
        </div>

        {story.own ? (
          <p className="text-[12px] text-muted2">{t(OWN)}</p>
        ) : rejecting ? (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault()
              onReject(note)
            }}
          >
            <label className="block text-xs font-medium text-muted2">
              {t('A note for the author (optional)')}
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={2000}
                rows={3}
                className="mt-1 w-full rounded-lg border border-border bg-cream p-2 text-sm text-ink"
              />
            </label>
            <div className="flex gap-2">
              <PillButton type="submit" className="!py-1.5 text-xs" disabled={disabled}>
                {busy ? t('Sending back…') : t('Send back to the author')}
              </PillButton>
              <PillButton
                type="button"
                variant="outline"
                className="!py-1.5 text-xs"
                disabled={busy}
                onClick={() => setRejecting(false)}
              >
                {t('Cancel')}
              </PillButton>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap gap-2">
            <PillButton
              type="button"
              variant="teal"
              className="!py-1.5 text-xs"
              disabled={disabled}
              onClick={onApprove}
              aria-label={message('Publish {title}: the label was wrong', { title: story.title })}
            >
              <Check size={13} /> {busy ? t('Publishing…') : t('Publish')}
            </PillButton>
            <PillButton
              type="button"
              variant="outline"
              className="!py-1.5 text-xs"
              disabled={disabled}
              onClick={() => setRejecting(true)}
              aria-label={message('Send {title} back to the author', { title: story.title })}
            >
              <X size={13} /> {t('Send back')}
            </PillButton>
          </div>
        )}
      </article>
    </Card>
  )
}
