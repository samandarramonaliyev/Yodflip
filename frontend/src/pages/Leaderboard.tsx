import { Send } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Avatar, EmptyState, ErrorState, ListSkeleton, Segmented } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { LeaderRow } from '../lib/types'
import { useApp } from '../store/app'

type Tab = 'weekly' | 'all' | 'daily'

function Row({ r, me, unit }: { r: LeaderRow; me: boolean; unit: string }) {
  const medal = r.rank === 1 ? '🥇' : r.rank === 2 ? '🥈' : r.rank === 3 ? '🥉' : null
  return (
    <li className={`flex items-center gap-3 px-3 py-2.5 ${me ? 'bg-primary-soft' : ''}`}>
      <span className="w-8 text-center font-black text-muted">{medal || r.rank}</span>
      <Avatar name={r.name} url={r.avatar_url} size={40} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 truncate font-extrabold">
          {r.name}
          {r.is_telegram && <Send className="h-3.5 w-3.5 shrink-0 text-[#229ED9]" aria-label="Telegram" />}
        </div>
        {r.telegram_username && <div className="truncate text-xs text-muted">@{r.telegram_username}</div>}
      </div>
      <span className="font-black">
        {r.score} <span className="text-xs text-muted">{unit}</span>
      </span>
    </li>
  )
}

export default function Leaderboard() {
  const t = useT()
  const [params] = useSearchParams()
  const track = useApp((s) => s.track)
  const user = useApp((s) => s.user)
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab) || 'weekly')
  const { data, error, loading, reload } = useAsync(
    () =>
      tab === 'daily'
        ? api.get<{ entries: LeaderRow[] }>('/games/daily/leaderboard/', { track }).then((r) => ({ entries: r.entries, me: null as LeaderRow | null }))
        : api.get<{ entries: LeaderRow[]; me: LeaderRow | null }>('/gamification/leaderboard/', { period: tab }),
    [tab, track],
  )
  const unit = tab === 'daily' ? t('lb.points') : 'XP'
  const meInList = data?.entries.some((e) => e.user_id === user?.id || e.is_me)
  return (
    <div className="page max-w-2xl space-y-4">
      <h1 className="h1">{t('nav.leaderboard')}</h1>
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'weekly', label: t('lb.weekly') },
          { value: 'all', label: t('lb.all') },
          { value: 'daily', label: `📅 ${t('lb.daily')}` },
        ]}
      />
      {tab === 'daily' && <p className="text-sm text-muted">{t('lb.daily_hint', { track: track.toUpperCase() })}</p>}
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading ? (
        <ListSkeleton rows={6} height="h-14" />
      ) : !data?.entries.length ? (
        <EmptyState emoji="🏆" title={t('lb.empty')} text={t('lb.empty_text')} />
      ) : (
        <>
          <ul className="divide-y divide-line overflow-hidden rounded-card bg-card shadow-soft">
            {data.entries.map((r) => (
              <Row key={`${r.rank}-${r.name}`} r={r} me={r.user_id === user?.id || Boolean(r.is_me)} unit={unit} />
            ))}
          </ul>
          {data.me && !meInList && (
            <ul className="overflow-hidden rounded-card bg-card shadow-soft">
              <Row r={data.me} me unit={unit} />
            </ul>
          )}
        </>
      )}
    </div>
  )
}
