import { useParams } from 'react-router-dom'
import { XpChart } from '../components/XpChart'
import { Avatar, ErrorState, ProgressBar, Skeleton } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { STATUS_ICON, type StudentDetail } from '../lib/classes'
import { useAsync, useTelegramBack } from '../lib/hooks'

/** Teacher → one student: only class-related stats (progress, mistakes, activity). */
export default function ClassStudent() {
  const t = useT()
  const { id = '', uid = '' } = useParams()
  useTelegramBack(`/classes/${id}`)
  const { data, error, reload } = useAsync(() => api.get<StudentDetail>(`/classes/${id}/students/${uid}/`), [id, uid])
  if (error)
    return (
      <div className="page">
        <ErrorState error={error} onRetry={reload} />
      </div>
    )
  if (!data)
    return (
      <div className="page space-y-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-48" />
      </div>
    )
  const s = data.student
  return (
    <div className="page space-y-4" data-testid="student-detail">
      <section className="card flex items-center gap-4 p-4">
        <Avatar name={s.name} url={s.avatar_url} size={56} />
        <div className="min-w-0 flex-1">
          <h1 className="h1 truncate">{s.name}</h1>
          <div className="text-sm text-muted">
            {t('cls.col_last_active')}: {s.last_active ?? '—'}
          </div>
        </div>
      </section>
      <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {[
          [t('cls.col_words_week'), s.words_week],
          [t('cls.col_words_total'), s.words_total],
          [t('cls.col_accuracy'), s.accuracy === null ? '—' : `${s.accuracy}%`],
          [t('cls.col_streak'), `🔥 ${s.streak}`],
        ].map(([label, value]) => (
          <div key={String(label)} className="card p-3">
            <div className="text-2xl font-black">{value}</div>
            <div className="text-xs text-muted">{label}</div>
          </div>
        ))}
      </section>
      <section className="card p-4">
        <h2 className="h2 mb-2">📈 {t('cls.activity')}</h2>
        <XpChart data={data.chart} />
      </section>
      <section className="space-y-2">
        <h2 className="h2">📝 {t('cls.assignments')}</h2>
        {data.assignments.map((a) => (
          <div key={a.id} className="card space-y-1 p-3">
            <div className="font-bold">
              {a.progress && STATUS_ICON[a.progress.status]} {a.title}
            </div>
            {a.progress && (
              <>
                <ProgressBar value={a.progress.target_percent} />
                <div className="text-xs text-muted">
                  {a.target_kind === 'plays' ? t('cls.plays_progress', { n: a.progress.plays, of: a.target_value }) : t('cls.words_progress', { n: a.progress.done, of: a.progress.total, pct: a.progress.percent })}
                </div>
              </>
            )}
          </div>
        ))}
      </section>
      <section className="card p-4">
        <h2 className="h2 mb-2">📊 {t('nav.levels')}</h2>
        <div className="grid grid-cols-5 gap-2">
          {data.levels.map((l) => (
            <div key={l.level} className="text-center">
              <div className="font-black">{l.level}</div>
              <ProgressBar value={l.percent} className="mt-1 h-1.5" />
              <div className="text-xs text-muted">{l.percent}%</div>
            </div>
          ))}
        </div>
      </section>
      <section className="card p-4">
        <h2 className="h2 mb-2">❌ {t('cls.mistakes')}</h2>
        {data.mistakes.length === 0 ? (
          <p className="text-sm text-muted">{t('cls.no_mistakes')}</p>
        ) : (
          <ul className="divide-y divide-line">
            {data.mistakes.map((m) => (
              <li key={m.term} className="flex justify-between gap-2 py-1.5 text-sm">
                <span>
                  <b>{m.term}</b> <span className="text-muted">— {m.translation}</span>
                </span>
                <span className="font-bold text-error">×{m.misses}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
