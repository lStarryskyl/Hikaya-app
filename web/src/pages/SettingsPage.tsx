import { t, useLocale, setLocale } from '../i18n'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { ArrowLeft, Bell, Eye, Globe2, Lock, LogOut, Moon, Save, User } from 'lucide-react'
import { Card, PillButton } from '../components/ui'
import { initials, useAuth } from '../auth'

export default function SettingsPage() {
  const language = useLocale()

  const { user } = useAuth()
  // Settings editing is mock in the demo: changes stay on this page and are not saved.
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [handle, setHandle] = useState(user?.email.split('@')[0] ?? '')
  const [bio, setBio] = useState(
    'Field collector and oral-history enthusiast documenting elders’ memories across Jordan.',
  )
  const [emailNotifs, setEmailNotifs] = useState(true)
  const [pushNotifs, setPushNotifs] = useState(true)
  const [mapPublic, setMapPublic] = useState(true)
  const [saved, setSaved] = useState(false)

  function save() {
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            to="/profile"
            className="mb-2 inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
          >
            <ArrowLeft className="rtl:rotate-180" size={12} /> {t('Back to profile')}
          </Link>
          <h1 className="font-serif text-2xl">{t('Settings')}</h1>
          <p className="text-sm text-muted">{t('Account, privacy, and notifications')}</p>
        </div>
        <PillButton variant="primary" className="!py-2 text-xs" onClick={save}>
          <Save size={13} /> {saved ? t('Saved') : t('Save changes')}
        </PillButton>
      </div>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <User size={16} className="text-terracotta" /> {t('Profile')}
        </div>
        <div className="flex items-center gap-3">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-terracotta-light font-semibold text-terracotta-dark">
            {initials(user?.display_name ?? '?')}
          </span>
          <div className="text-xs text-muted">{t('Avatar is managed on your Profile page.')}</div>
        </div>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Display name')}
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-cream px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-terracotta/30"
          />
        </label>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Handle')}
          <div className="mt-1 flex items-center rounded-lg border border-border bg-cream px-3 py-2">
            <span className="text-sm text-muted">@</span>
            <input
              value={handle}
              onChange={(e) => setHandle(e.target.value.replace(/\s+/g, '_'))}
              className="w-full bg-transparent text-sm outline-none"
            />
          </div>
        </label>
        <label className="block text-start text-xs font-medium text-muted2">
          {t('Bio')}
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-border bg-cream px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-terracotta/30"
          />
        </label>
      </Card>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Bell size={16} className="text-terracotta" /> {t('Notifications')}
        </div>
        <ToggleRow
          label="Email notifications"
          hint="Likes, comments, and archive reminders"
          checked={emailNotifs}
          onChange={setEmailNotifs}
        />
        <ToggleRow
          label="Push notifications"
          hint="Nearby stories and map activity"
          checked={pushNotifs}
          onChange={setPushNotifs}
        />
        <Link to="/notifications" className="inline-block text-xs font-medium text-terracotta">
          {t('Open notification inbox →')}
        </Link>
      </Card>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Lock size={16} className="text-terracotta" /> {t('Privacy')}
        </div>
        <ToggleRow
          label="Show my pins on the public map"
          hint="Others can discover your published stories geographically"
          checked={mapPublic}
          onChange={setMapPublic}
        />
        <div className="flex items-start gap-2 rounded-lg bg-cream px-3 py-2 text-[12px] text-muted2">
          <Eye size={14} className="mt-0.5 shrink-0" />
          {t('Unpublished drafts stay private until you tap Publish.')}
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Globe2 size={16} className="text-terracotta" /> {t('Language & display')}
        </div>
        <div className="flex gap-2">
          {(['en', 'ar'] as const).map((lang) => (
            <button
              key={lang}
              type="button"
              onClick={() => setLocale(lang)}
              className={`rounded-full border px-4 py-2 text-xs font-medium ${
                language === lang
                  ? 'border-terracotta bg-terracotta text-cream'
                  : 'border-border text-muted2 hover:bg-cream'
              }`}
            >
              {lang === 'en' ? t('English') : 'العربية'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <Moon size={13} /> {t('Theme follows system for now.')}
        </div>
      </Card>

      <button
        type="button"
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-3 text-sm text-muted2 hover:bg-cream"
      >
        <LogOut size={15} /> {t('Sign out (demo)')}
      </button>
    </div>
  )
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  useLocale()

  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="text-sm font-medium">{t(label)}</div>
        <div className="text-[12px] text-muted">{hint}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${
          checked ? 'bg-terracotta' : 'bg-border'
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
            checked ? 'start-5' : 'start-0.5'
          }`}
        />
      </button>
    </div>
  )
}
