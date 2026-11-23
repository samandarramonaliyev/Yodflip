import { Link } from 'react-router-dom'
import { useT } from '../i18n'
import type { DuelStats } from '../lib/duel'
import { Avatar } from './ui'

const ICON = { win: '🏆', draw: '🤝', loss: '😅' }

/** "Duellar: 12 g'alaba · 5 mag'lubiyat", recent duels, top rivals, invited friends. */
export function DuelStatsCard({ stats }: { stats: DuelStats }) {
  const t = useT()
  return (
    <div className="card space-y-4 p-4" data-testid="duel-stats">
      <div>
        <h2 className="h2">⚔️ {t('duel.record', { wins: stats.wins, losses: stats.losses })}</h2>
        {stats.draws > 0 && <p className="text-sm text-muted">{t('duel.draws', { n: stats.draws })}</p>}
        <p className="mt-1 text-sm font-bold text-primary">🤝 {t('duel.invited', { n: stats.invited })}</p>
      </div>
      {stats.recent.length > 0 && (
        <div>
          <div className="mb-1 font-bold">{t('duel.recent')}</div>
          <ul className="space-y-1.5">
            {stats.recent.slice(0, 5).map((d) => (
              <li key={d.code}>
                <Link to={`/duel/${d.code}`} className="flex min-h-[44px] items-center gap-2 rounded-xl bg-line/50 px-3 text-sm font-bold">
                  <span>{ICON[d.outcome]}</span>
                  <span className="min-w-0 flex-1 truncate">{d.other.name || t('duel.guest')}</span>
                  <span className="font-black">
                    {d.my_score}:{d.other_score}
                  </span>
                  <span className="text-xs text-muted">{d.track.toUpperCase()}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {stats.rivals.length > 0 && (
        <div>
          <div className="mb-1 font-bold">{t('duel.rivals')}</div>
          <ul className="space-y-1.5">
            {stats.rivals.map((r, i) => (
              <li key={i} className="flex min-h-[40px] items-center gap-2 text-sm font-bold">
                <Avatar name={r.name} url={r.avatar_url} size={28} />
                <span className="min-w-0 flex-1 truncate">{r.name}</span>
                <span className="text-success">{r.wins}</span>:<span className="text-error">{r.losses}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
