import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { GoalCard } from '../components/GoalCard'
import { EmptyState, ErrorState, ListSkeleton, ProgressBar } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import type { ExamPackRow } from '../lib/exams'
import { useAsync } from '../lib/hooks'
import { useApp } from '../store/app'

export default function Exams() {
  const t = useT()
  const track = useApp((s) => s.track)
  const lang = useApp((s) => s.lang)
  const { data, error, loading, reload } = useAsync(() => api.get<{ packs: ExamPackRow[] }>('/exams/', { track }), [track])
  return (
    <div className="page max-w-3xl space-y-4">
      <h1 className="h1">📘 {t('exam.title')}</h1>
      <p className="text-muted">{t('exam.intro')}</p>
      <GoalCard />
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading || !data ? (
        <ListSkeleton rows={3} height="h-28" />
      ) : !data.packs.length ? (
        <EmptyState emoji="📘" title={t('exam.none')} />
      ) : (
        <div className="grid gap-3">
          {data.packs.map((p) => (
            <Link key={p.slug} to={`/exams/${p.slug}`} className="card flex items-center gap-4 p-5 transition hover:shadow-lift" data-testid="exam-pack">
              <span className="text-4xl">{p.emoji}</span>
              <span className="min-w-0 flex-1 space-y-1.5">
                <span className="block text-lg font-black">{p.name[lang]}</span>
                <span className="block text-sm text-muted">{t('exam.counts', { words: p.total, topics: p.topic_count })}</span>
                <ProgressBar value={p.percent} className="h-2" />
                <span className="block text-xs font-bold text-primary">
                  {p.found} / {p.total} · {p.percent}%
                </span>
              </span>
              <ChevronRight className="shrink-0 text-muted" />
            </Link>
          ))}
        </div>
      )}
      <p className="text-xs text-muted">{t('exam.disclaimer')}</p>
    </div>
  )
}
