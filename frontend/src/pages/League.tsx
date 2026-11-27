import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Avatar, EmptyState, ErrorState, Skeleton } from '../components/ui'
import { ShareButton } from '../components/ShareSheet'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useTelegramBack } from '../lib/hooks'
import { countdown, LIVE_REFRESH_MS, resultKey, secondsLeft, type LeagueState, type Tier, type WeekResult } from '../lib/league'
import { useApp } from '../store/app'

/** Refetch on focus and every 30 s (no websockets). */
function useLiveLeague() {
  const [data, setData] = useState<LeagueState | null>(null)
  const [error, setError] = useState<unknown>(null)
  const fetchedAt = useRef(Date.now())
  const load = useCallback(async () => {
    try {
      const d = await api.get<LeagueState>('/leagues/')
      fetchedAt.current = Date.now()
      setData(d)
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [])
  useEffect(() => {
    void load()
    const timer = window.setInterval(() => document.visibilityState === 'visible' && void load(), LIVE_REFRESH_MS)
    const onFocus = () => void load()
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
  }, [load])
  return { data, error, reload: load, fetchedAt }
}

function TierBadge({ tier, size = 'lg' }: { tier: Tier; size?: 'lg' | 'sm' }) {
  const lang = useApp((s) => s.lang)
  return (
    <span className={`inline-flex items-center gap-1 font-black ${size === 'lg' ? 'text-2xl' : 'text-sm'}`}>
      <span>{tier.emoji}</span> {tier.name[lang]}
    </span>
  )
}

export function Countdown({ seconds }: { seconds: number }) {
  const t = useT()
  const c = countdown(seconds)
  return <span data-testid="countdown">{c.days > 0 ? t('league.left_days', { d: c.days, h: c.hours }) : t('league.left_hours', { h: c.hours, m: c.minutes })}</span>
}

export function ResultLine({ r }: { r: WeekResult }) {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const tier = r.new_tier ?? r.tier
  return <span>{t(resultKey(r), { tier: `${tier.emoji} ${tier.name[lang]}`, rank: r.rank ?? '—' })}</span>
}

export default function League() {
  const t = useT()
  const lang = useApp((s) => s.lang)
  useTelegramBack('/')
  const { data, error, reload, fetchedAt } = useLiveLeague()
  const [, tick] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => tick((x) => x + 1), 30_000)
    return () => window.clearInterval(id)
  }, [])
  const [tab, setTab] = useState<'week' | 'history'>('week')
  const [history, setHistory] = useState<WeekResult[] | null>(null)
  useEffect(() => {
    if (tab === 'history' && history === null) void api.get<{ weeks: WeekResult[] }>('/leagues/history/').then((r) => setHistory(r.weeks), () => setHistory([]))
  }, [tab, history])

  if (error && !data) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>
  if (!data)
    return (
      <div className="page space-y-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-96" />
      </div>
    )
  const left = secondsLeft(data, fetchedAt.current)
  const z = data.zones
  return (
    <div className="page space-y-4">
      <section className="card relative overflow-hidden p-5 text-center" style={{ background: `linear-gradient(135deg, ${data.tier.color}33, transparent)` }}>
        <div className="text-6xl">{data.tier.emoji}</div>
        <h1 className="h1 mt-1">{t('league.title', { tier: data.tier.name[lang] })}</h1>
        <p className="mt-1 font-bold text-muted">
          ⏳ <Countdown seconds={left} />
        </p>
        <div className="mt-3 flex flex-wrap justify-center gap-1">
          {data.tiers.map((x) => (
            <span key={x.code} className={`chip ${x.code === data.tier.code ? 'bg-primary text-white' : 'bg-line opacity-70'}`}>
              {x.emoji} {x.name[lang]}
            </span>
          ))}
        </div>
        {data.trophies > 0 && <p className="mt-2 text-sm font-black">🏆 × {data.trophies}</p>}
      </section>

      {data.last_result && (
        <div className="card flex items-center gap-3 p-3 text-sm font-bold" data-testid="last-result">
          <span className="text-2xl">{data.last_result.result === 'trophy' ? '🏆' : data.last_result.result === 'promoted' ? '🎉' : data.last_result.result === 'demoted' ? '📉' : '🙂'}</span>
          <span className="flex-1">
            {t('league.last_week')}: <ResultLine r={data.last_result} />
          </span>
          {(data.last_result.result === 'promoted' || data.last_result.result === 'trophy') && (
            <ShareButton
              className="btn-soft min-h-[40px] px-3"
              input={{
                template: 'league',
                tierEmoji: (data.last_result.new_tier ?? data.last_result.tier).emoji,
                tierName: (data.last_result.new_tier ?? data.last_result.tier).name[lang],
                result: data.last_result.result,
                rank: data.last_result.rank ?? 1,
                xp: data.last_result.xp,
              }}
            />
          )}
        </div>
      )}

      <div className="flex gap-1">
        <button className={`chip ${tab === 'week' ? 'bg-primary text-white' : 'bg-line'}`} onClick={() => setTab('week')}>
          {t('league.this_week')}
        </button>
        <button className={`chip ${tab === 'history' ? 'bg-primary text-white' : 'bg-line'}`} onClick={() => setTab('history')}>
          {t('league.history')}
        </button>
      </div>

      {tab === 'history' ? (
        history === null ? (
          <Skeleton className="h-40" />
        ) : history.length === 0 ? (
          <p className="text-muted">{t('league.no_history')}</p>
        ) : (
          <ul className="card divide-y divide-line" data-testid="league-history">
            {history.map((h) => (
              <li key={h.week} className="flex items-center gap-3 px-4 py-3 text-sm">
                <span className="w-24 font-bold text-muted">{h.week}</span>
                <TierBadge tier={h.tier} size="sm" />
                <span className="flex-1 text-right">
                  #{h.rank} · {h.xp} XP · <ResultLine r={h} />
                </span>
              </li>
            ))}
          </ul>
        )
      ) : !data.joined || !z ? (
        <EmptyState emoji="🏁" title={t('league.not_joined')} text={t('league.not_joined_text')} action={<Link className="btn-primary" to="/games">{t('nav.games')}</Link>} />
      ) : (
        <>
          {data.me && data.me.zone === 'demote' && data.me.need_xp > 0 && (
            <div className="card border-2 border-error/40 p-3 text-sm font-bold text-error" data-testid="danger">
              ⚠️ {t('league.danger', { xp: data.me.need_xp })}
            </div>
          )}
          <ol className="card divide-y divide-line overflow-hidden" data-testid="league-group">
            {data.group.map((r, i) => (
              <li key={r.user_id}>
                {i === z.promote && z.promote > 0 && <div className="bg-success/10 px-4 py-1 text-center text-xs font-black text-success">▲ {z.top_tier ? t('league.trophy_zone') : t('league.promotion_zone')}</div>}
                {i === z.size - z.demote && z.demote > 0 && <div className="bg-error/10 px-4 py-1 text-center text-xs font-black text-error">▼ {t('league.demotion_zone')}</div>}
                <div
                  data-zone={r.zone}
                  className={`flex items-center gap-3 px-4 py-2 ${r.zone === 'promote' ? 'bg-success/10' : r.zone === 'demote' ? 'bg-error/10' : ''} ${r.is_me ? 'font-black ring-2 ring-inset ring-primary' : ''}`}
                >
                  <span className="w-7 text-center font-black">{r.rank}</span>
                  <Avatar name={r.name} url={r.avatar_url} size={32} />
                  <span className="flex-1 truncate">
                    {r.name} {r.is_me && <span className="text-xs text-primary">({t('league.you')})</span>}
                  </span>
                  <span className="font-black">{r.xp} XP</span>
                </div>
              </li>
            ))}
          </ol>
          <p className="text-center text-xs text-muted">{t('league.rules', { up: z.promote, down: z.demote })}</p>
        </>
      )}
    </div>
  )
}
