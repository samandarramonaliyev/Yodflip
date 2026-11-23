import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import { ALL_LANGS, LANG_META, type TrLang } from '../lib/translation'
import { Segmented, Skeleton, Toggle, toast } from './ui'

interface QuizSettings {
  enabled: boolean
  hour: number
  timezone: string
  questions: 5 | 8 | 10
  translation_lang: TrLang | ''
  quiet_days: number[]
  bot_blocked: boolean
}

const ZONES = ['Asia/Tashkent', 'Asia/Samarkand', 'Asia/Almaty', 'Asia/Bishkek', 'Asia/Dushanbe', 'Asia/Seoul', 'Asia/Dubai', 'Europe/Moscow', 'Europe/Istanbul', 'Europe/Berlin', 'Europe/London', 'America/New_York']

function browserZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null
  } catch {
    return null
  }
}

/** Daily quiz in the Telegram chat: on/off, hour, timezone, number of questions, language, quiet days. */
export function QuizSettingsCard({ linked }: { linked: boolean }) {
  const t = useT()
  const { data, setData } = useAsync(() => api.get<QuizSettings>('/quiz/settings/'), [])
  if (!data) return <Skeleton className="h-40" />
  const patch = async (p: Partial<QuizSettings>) => {
    const before = data
    setData({ ...data, ...p })
    try {
      setData(await api.patch<QuizSettings>('/quiz/settings/', p))
    } catch {
      setData(before)
      toast.err(t('err.generic'))
    }
  }
  const zones = [...new Set([data.timezone, browserZone() ?? data.timezone, ...ZONES])]
  const days = t('quiz.days').split(' ')
  return (
    <section className="card space-y-3 p-4" data-testid="quiz-settings">
      <div>
        <h2 className="h2">🧠 {t('quiz.title')}</h2>
        <p className="text-sm text-muted">{linked ? t('quiz.hint') : t('profile.reminder_need_tg')}</p>
        {data.bot_blocked && <p className="text-sm font-bold text-error">{t('quiz.blocked')}</p>}
      </div>
      <Toggle checked={data.enabled} onChange={(enabled) => void patch({ enabled })} label={t('quiz.enabled')} />
      {data.enabled && (
        <>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="block font-bold">{t('quiz.hour')}</span>
              <select className="input" value={data.hour} onChange={(e) => void patch({ hour: Number(e.target.value) })}>
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>
                    {String(h).padStart(2, '0')}:00
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="block font-bold">{t('quiz.timezone')}</span>
              <select className="input" value={data.timezone} onChange={(e) => void patch({ timezone: e.target.value })}>
                {zones.map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div>
            <div className="mb-1 font-bold">{t('quiz.count')}</div>
            <Segmented
              value={String(data.questions)}
              onChange={(v) => void patch({ questions: Number(v) as QuizSettings['questions'] })}
              options={['5', '8', '10'].map((n) => ({ value: n, label: n }))}
            />
          </div>
          <div>
            <div className="mb-1 font-bold">{t('quiz.lang')}</div>
            <Segmented
              value={data.translation_lang || 'auto'}
              onChange={(v) => void patch({ translation_lang: v === 'auto' ? '' : (v as TrLang) })}
              options={[{ value: 'auto', label: t('quiz.lang_auto') }, ...ALL_LANGS.map((l) => ({ value: l as string, label: LANG_META[l].flag }))]}
            />
          </div>
          <div>
            <div className="mb-1 font-bold">{t('quiz.quiet')}</div>
            <div className="grid grid-cols-7 gap-1">
              {days.map((d, i) => {
                const on = data.quiet_days.includes(i)
                return (
                  <button
                    key={d}
                    aria-pressed={on}
                    onClick={() => void patch({ quiet_days: on ? data.quiet_days.filter((x) => x !== i) : [...data.quiet_days, i] })}
                    className={`min-h-[44px] rounded-xl text-sm font-black ${on ? 'bg-tint text-tint-ink' : 'bg-line'}`}
                  >
                    {d}
                  </button>
                )
              })}
            </div>
          </div>
        </>
      )}
      <p className="text-xs text-muted">{t('quiz.bot_hint')}</p>
    </section>
  )
}
