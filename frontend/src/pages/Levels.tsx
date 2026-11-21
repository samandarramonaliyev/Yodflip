import { motion } from 'framer-motion'
import { ChevronRight, Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorState, ListSkeleton, ProgressBar } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { LevelRow } from '../lib/types'
import { useApp } from '../store/app'

export default function Levels() {
  const t = useT()
  const track = useApp((s) => s.track)
  const { data, error, loading, reload } = useAsync(() => api.get<{ levels: LevelRow[] }>('/words/levels/', { track }), [track])
  return (
    <div className="page space-y-5">
      <div>
        <h1 className="h1">{t('levels.title')}</h1>
        <p className="text-muted">{t(track === 'en' ? 'levels.subtitle_en' : 'levels.subtitle_de')}</p>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading || !data ? (
        <ListSkeleton rows={5} height="h-24" />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.levels.map((lv, i) => (
            <motion.div key={lv.level} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              {lv.unlocked ? (
                <Link to={`/levels/${lv.level}`} className="card flex items-center gap-4 p-4 transition hover:shadow-lift">
                  <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-tint text-2xl font-black text-tint-ink">{lv.level}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex justify-between font-black">
                      <span>{t(`cefr.${lv.level}`)}</span>
                      <span className="text-primary">{lv.percent}%</span>
                    </div>
                    <div className="mb-2 text-sm text-muted">
                      {t('level.count', { n: lv.found, total: lv.total })} · {lv.completed ? '🎓' : lv.to_unlock > 0 ? t('level.to_unlock_short', { n: lv.to_unlock }) : '🔓'}
                    </div>
                    <ProgressBar value={lv.percent} color={lv.percent >= 70 ? 'bg-success' : 'bg-primary'} />
                  </div>
                  <ChevronRight className="text-muted" />
                </Link>
              ) : (
                <div className="card flex items-center gap-4 p-4 opacity-60">
                  <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-line text-2xl font-black text-muted">{lv.level}</span>
                  <div className="flex-1">
                    <div className="font-black">{t(`cefr.${lv.level}`)}</div>
                    <div className="text-sm text-muted">{t('levels.locked_hint')}</div>
                  </div>
                  <Lock className="text-muted" />
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
