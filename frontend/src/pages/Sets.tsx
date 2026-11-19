import { Camera, ChevronRight, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, ListSkeleton } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { WordSet } from '../lib/types'
import { useApp } from '../store/app'

export default function Sets() {
  const t = useT()
  const track = useApp((s) => s.track)
  const { data, error, loading, reload } = useAsync(() => api.get<WordSet[]>('/sets/', { track }), [track])
  return (
    <div className="page max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="h1">{t('sets.title')}</h1>
        <Link to="/scan" className="btn-primary">
          <Camera className="h-5 w-5" /> {t('nav.scan')}
        </Link>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading ? (
        <ListSkeleton rows={4} />
      ) : !data?.length ? (
        <EmptyState emoji="📸" title={t('sets.empty')} text={t('sets.empty_text')} action={<Link to="/scan" className="btn-primary">{t('scan.title')}</Link>} />
      ) : (
        <ul className="space-y-2">
          {data.map((s) => (
            <li key={s.id} className="card flex items-center gap-3 p-3">
              <Link to={`/sets/${s.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary-soft text-xl">📄</span>
                <div className="min-w-0">
                  <div className="truncate font-black">{s.name}</div>
                  <div className="text-sm text-muted">
                    {t('sets.pairs_n', { n: s.pair_count })} · {new Date(s.created_at).toLocaleDateString()}
                  </div>
                </div>
              </Link>
              <Link to={`/play/match?source=set&id=${s.id}`} className="grid h-11 w-11 place-items-center rounded-full bg-primary text-white" aria-label={t('sets.play_match')}>
                <Play className="h-5 w-5" />
              </Link>
              <ChevronRight className="hidden text-muted sm:block" />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
