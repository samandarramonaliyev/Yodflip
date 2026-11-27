import { LANG_META } from '../lib/translation'
import { Flame, LogOut, Moon, Send, Star, Sun, Target, Trophy } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { TrackSwitch } from '../components/Layout'
import { DuelStatsCard } from '../components/DuelStatsCard'
import { CreateClassSheet } from './Classes'
import { ShareButton } from '../components/ShareSheet'
import { referralLink } from '../lib/share'
import { QuizSettingsCard } from '../components/QuizSettingsCard'
import { TtsSettings } from '../components/TtsSettings'
import { WordListsSection } from '../components/WordListsSection'
import { XpChart } from '../components/XpChart'
import { Avatar, ErrorState, ProgressBar, Segmented, Skeleton, Toggle, toast } from '../components/ui'
import { LANG_NAMES, useT } from '../i18n'
import { api } from '../lib/api'
import type { DuelStats } from '../lib/duel'
import { useAsync } from '../lib/hooks'
import { isTelegram } from '../lib/telegram'
import type { Achievement, Cefr, ProfileStats, UiLang, User } from '../lib/types'
import { useApp, type ThemePref } from '../store/app'

const CEFRS: Cefr[] = ['A1', 'A2', 'B1', 'B2', 'C1']

function LinkTelegram() {
  const t = useT()
  const config = useApp((s) => s.config)
  const setUser = useApp((s) => s.setUser)
  const ref = useRef<HTMLDivElement>(null)
  const link = async (payload: Record<string, unknown>) => {
    try {
      setUser(await api.post<User>('/auth/telegram/link/', payload))
      toast.ok(t('profile.tg_linked'))
    } catch {
      toast.err(t('auth.tg_failed'))
    }
  }
  useEffect(() => {
    if (!config?.bot_username || !ref.current) return
    window.onTelegramAuth = (u) => void link({ widget: u })
    const s = document.createElement('script')
    s.src = 'https://telegram.org/js/telegram-widget.js?22'
    s.async = true
    s.setAttribute('data-telegram-login', config.bot_username)
    s.setAttribute('data-size', 'medium')
    s.setAttribute('data-onauth', 'onTelegramAuth(user)')
    ref.current.innerHTML = ''
    ref.current.appendChild(s)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config?.bot_username])
  if (config?.bot_username) return <div ref={ref} />
  if (config?.telegram_mock)
    return (
      <button className="btn bg-[#229ED9] text-white" onClick={() => link({ init_data: '' })}>
        <Send className="h-4 w-4" /> {t('profile.link_tg_demo')}
      </button>
    )
  return <p className="text-sm text-muted">{t('profile.tg_not_configured')}</p>
}

function SetEmail() {
  const t = useT()
  const setUser = useApp((s) => s.setUser)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      setUser(await api.post<User>('/auth/set-email/', { email, password }))
      toast.ok(t('common.saved'))
    } catch {
      toast.err(t('auth.email_taken'))
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
      <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t('auth.email')} />
      <input className="input" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t('auth.password')} />
      <button className="btn-primary">{t('common.save')}</button>
    </form>
  )
}

export default function Profile() {
  const t = useT()
  const { track, user, lang, setLang, theme, setTheme, muted, toggleMute, logout, setUser, config } = useApp()
  const stats = useAsync(() => api.get<ProfileStats>('/gamification/profile/', { track }), [track])
  const ach = useAsync(() => api.get<Achievement[]>('/gamification/achievements/'), [])
  const duels = useAsync(() => api.get<DuelStats>('/duels/'), [])
  const [reminder, setReminder] = useState(user?.reminder_time?.slice(0, 5) || '')
  const [classSheet, setClassSheet] = useState(false)

  if (!user) return null
  const d = stats.data
  const pct = d ? Math.round((100 * (d.xp - d.level_floor)) / Math.max(1, d.level_ceil - d.level_floor)) : 0
  const cefrKey = track === 'en' ? 'cefr_level_en' : 'cefr_level_de'

  const patch = async (p: Partial<User>) => {
    try {
      setUser(await api.patch<User>('/auth/me/', p))
      toast.ok(t('common.saved'))
    } catch {
      toast.err(t('err.generic'))
    }
  }

  return (
    <div className="page space-y-5">
      <section className="card flex flex-wrap items-center gap-4 p-5">
        <Avatar name={user.display_name} url={user.avatar_url} size={64} />
        <div className="min-w-0 flex-1">
          <h1 className="h1 truncate">{user.display_name}</h1>
          <div className="text-sm text-muted">
            {user.telegram_username ? `@${user.telegram_username}` : user.email}
          </div>
        </div>
        <TrackSwitch />
      </section>

      {stats.error ? (
        <ErrorState error={stats.error} onRetry={stats.reload} />
      ) : !d ? (
        <div className="grid gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="card p-4">
              <Star className="h-6 w-6 fill-accent text-accent" />
              <div className="mt-1 text-2xl font-black">{t('profile.level_n', { n: d.level })}</div>
              <div className="text-xs text-muted">{d.xp} XP</div>
              <ProgressBar value={pct} color="bg-accent" className="mt-2 h-1.5" />
            </div>
            <div className="card p-4">
              <Flame className={`h-6 w-6 ${d.streak ? 'fill-orange-400 text-orange-500' : 'text-muted'}`} />
              <div className="mt-1 text-2xl font-black">{d.streak}</div>
              <div className="text-xs text-muted">{t('profile.streak_best', { n: d.best_streak })}</div>
            </div>
            <div className="card p-4">
              <Trophy className="h-6 w-6 text-primary" />
              <div className="mt-1 text-2xl font-black">{d.total_words}</div>
              <div className="text-xs text-muted">{t('profile.total_words', { n: d.learned })}</div>
            </div>
            <div className="card p-4">
              <Target className="h-6 w-6 text-success" />
              <div className="mt-1 text-2xl font-black">{d.accuracy}%</div>
              <div className="text-xs text-muted">{t('res.accuracy')}</div>
            </div>
          </section>
          {d.translation_langs && d.translation_langs.length > 0 && (
            <p className="card px-4 py-3 text-sm font-bold" data-testid="played-in">
              🌐 {t('profile.played_in')}: {d.translation_langs.map((r) => `${LANG_META[r.lang].short} ${r.percent}%`).join(', ')}
            </p>
          )}
          <section className="grid gap-3 md:grid-cols-[2fr_1fr]">
            <div className="card min-w-0 p-4">
              <XpChart data={d.chart} />
            </div>
            <div className="card space-y-3 p-4">
              <h2 className="h2">{t('profile.track_level')}</h2>
              <div className="text-sm font-bold text-muted">{track === 'en' ? 'EN · English' : 'DE · Deutsch'}</div>
              <div className="grid grid-cols-5 gap-1">
                {CEFRS.map((c) => (
                  <button key={c} onClick={() => patch({ [cefrKey]: c } as Partial<User>)} className={`min-h-[44px] rounded-xl text-sm font-black ${d.cefr === c ? 'bg-tint text-tint-ink' : 'bg-line'}`}>
                    {c}
                  </button>
                ))}
              </div>
              <Link to="/play/review" className="btn-soft w-full">
                🔁 {t('home.due')}: {d.due}
              </Link>
            </div>
          </section>
        </>
      )}

      <section className="grid gap-3 sm:grid-cols-2" data-testid="profile-classes">
        <Link to="/classes" className="card flex items-center gap-3 p-4 font-black transition hover:shadow-lift">
          <span className="text-3xl">🏫</span> {t('cls.my_classes')}
        </Link>
        <button className="card flex items-center gap-3 p-4 text-left font-black transition hover:shadow-lift" onClick={() => setClassSheet(true)}>
          <span className="text-3xl">👩‍🏫</span> {t('cls.create')}
        </button>
      </section>
      <CreateClassSheet open={classSheet} onClose={() => setClassSheet(false)} data={null} />

      {d?.week && (
        <section className="card flex flex-wrap items-center gap-3 p-4" data-testid="profile-week">
          <div className="min-w-0 flex-1">
            <div className="font-black">📊 {t('share.k_weekly')}</div>
            <div className="text-sm text-muted">
              {d.week.xp} XP · {t('share.words')}: {d.week.words} · {t('share.accuracy')}: {d.week.accuracy}%
            </div>
          </div>
          <ShareButton input={{ template: 'weekly', xp: d.week.xp, words: d.week.words, accuracy: d.week.accuracy, streak: d.streak }} />
        </section>
      )}

      <section className="card flex flex-wrap items-center gap-3 p-4" data-testid="profile-invites">
        <span className="text-3xl">🤝</span>
        <div className="min-w-0 flex-1">
          <div className="font-black">{t('share.invited', { n: d?.invited ?? 0 })}</div>
          <div className="text-xs text-muted">{t('share.invite_hint')}</div>
        </div>
        <button className="btn-soft" onClick={() => void navigator.clipboard?.writeText(referralLink(user.referral_code, config, window.location.origin)).then(() => toast.ok(t('share.copied')))}>
          🔗 {t('share.copy_link')}
        </button>
      </section>

      {duels.data && <DuelStatsCard stats={duels.data} />}

      <div className="card p-4">
        <WordListsSection track={track} />
      </div>

      <section className="card p-4">
        <h2 className="h2 mb-3">{t('profile.achievements')}</h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
          {(ach.data || []).map((a) => (
            <div key={a.code} className={`flex flex-col items-center gap-1 rounded-2xl p-3 text-center ${a.unlocked ? 'bg-accent/25' : 'bg-line/50 opacity-50 grayscale'}`} title={t(`ach.${a.code}_desc`)}>
              <span className="text-3xl">{a.emoji}</span>
              <span className="text-xs font-extrabold leading-tight">{t(`ach.${a.code}`)}</span>
            </div>
          ))}
        </div>
      </section>

      <QuizSettingsCard linked={user.is_telegram_linked} />

      <section className="card space-y-4 p-4">
        <h2 className="h2">{t('profile.settings')}</h2>
        <div>
          <div className="mb-1 font-bold">{t('profile.ui_language')}</div>
          <Segmented value={lang} onChange={(l: UiLang) => setLang(l)} options={(Object.keys(LANG_NAMES) as UiLang[]).map((l) => ({ value: l, label: LANG_NAMES[l] }))} />
        </div>
        {!isTelegram && (
          <div>
            <div className="mb-1 font-bold">{t('profile.theme')}</div>
            <Segmented
              value={theme}
              onChange={(v: ThemePref) => setTheme(v)}
              options={[
                { value: 'system', label: t('profile.theme_system') },
                { value: 'light', label: <Sun className="mx-auto h-4 w-4" /> },
                { value: 'dark', label: <Moon className="mx-auto h-4 w-4" /> },
              ]}
            />
          </div>
        )}
        <Toggle checked={!muted} onChange={toggleMute} label={t('profile.sound')} />
        {user.is_telegram_linked && <Toggle checked={user.notify_classes !== false} onChange={(v) => patch({ notify_classes: v })} label={t('profile.notify_classes')} />}
        {user.is_telegram_linked && <Toggle checked={user.notify_leagues !== false} onChange={(v) => patch({ notify_leagues: v })} label={t('profile.notify_leagues')} />}
        <TtsSettings />
        <div className="space-y-1">
          <div className="font-bold">{t('profile.reminder')}</div>
          <p className="text-sm text-muted">{user.is_telegram_linked ? t('profile.reminder_hint') : t('profile.reminder_need_tg')}</p>
          <div className="flex gap-2">
            <input type="time" className="input max-w-[160px]" value={reminder} onChange={(e) => setReminder(e.target.value)} disabled={!user.is_telegram_linked} />
            <button className="btn-soft" disabled={!user.is_telegram_linked} onClick={() => patch({ reminder_time: reminder || null })}>
              {t('common.save')}
            </button>
          </div>
        </div>
        <div className="space-y-2 border-t border-line pt-4">
          <div className="font-bold">{t('profile.accounts')}</div>
          <div className="text-sm">
            ✉️ {user.email || <span className="text-muted">{t('profile.no_email')}</span>}
            <br />✈️ {user.is_telegram_linked ? `Telegram ${user.telegram_username ? '@' + user.telegram_username : '✓'}` : <span className="text-muted">{t('profile.no_tg')}</span>}
          </div>
          {!user.is_telegram_linked && <LinkTelegram />}
          {!user.email && <SetEmail />}
        </div>
        {!isTelegram && (
          <button className="btn-danger w-full" onClick={logout}>
            <LogOut className="h-5 w-5" /> {t('auth.logout')}
          </button>
        )}
      </section>
    </div>
  )
}
