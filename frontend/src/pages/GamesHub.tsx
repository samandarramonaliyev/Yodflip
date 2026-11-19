import { Link } from 'react-router-dom'
import { GAMES } from '../games/catalog'
import { isAvailable, modeFor } from '../games/direction'
import { useT } from '../i18n'
import { useApp } from '../store/app'

export default function GamesHub() {
  const t = useT()
  const track = useApp((s) => s.track)
  return (
    <div className="page space-y-5">
      <h1 className="h1">{t('nav.games')}</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {GAMES.map((g) => {
          const ok = isAvailable(g.id, track)
          const mode = modeFor(g.id)
          return (
            <Link
              key={g.id}
              to={ok ? `/play/${g.id}` : '#'}
              aria-disabled={!ok}
              className={`card flex gap-4 p-4 transition ${ok ? 'hover:shadow-lift' : 'pointer-events-none opacity-50'}`}
            >
              <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-3xl ${g.color}`}>{g.emoji}</span>
              <div className="min-w-0">
                <div className="font-black">{t(`game.${g.id}`)}</div>
                <div className="text-sm text-muted">{t(`game.${g.id}_desc`)}</div>
                <span className="chip mt-2 bg-line text-xs text-muted">
                  {mode === 'definition' ? t('mode.definition') : mode === 'article' ? t('mode.article') : t('mode.memorize')}
                </span>
                {!ok && <div className="mt-1 text-xs font-bold text-error">{t('game.german_only')}</div>}
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
