import { Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useT } from '../i18n'
import { api } from '../lib/api'
import type { ExamGoal } from '../lib/exams'
import { useAsync } from '../lib/hooks'
import { useApp } from '../store/app'
import { ProgressBar } from './ui'

/** "Bugun Goethe A1 dan 15 ta so'z" (hidden when no goal is set). */
export function GoalCard() {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const { data } = useAsync(() => api.get<{ goal: ExamGoal | null }>('/exams/goal/'), [])
  const g = data?.goal
  if (!g) return null
  return (
    <Link to={`/exams/${g.slug}`} className="card flex items-center gap-4 p-4 transition hover:shadow-lift" data-testid="exam-goal">
      <div className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ${g.reached ? 'bg-success/20' : 'bg-primary-soft'}`}>
        {g.reached ? <span className="text-2xl">✅</span> : <Target className="h-6 w-6 text-primary" />}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="font-black">{t(g.reached ? 'exam.goal_reached' : 'exam.goal_today', { name: g.name[lang], n: g.per_day })}</div>
        <ProgressBar value={Math.round((100 * g.done) / g.per_day)} className="h-2" color={g.reached ? 'bg-success' : 'bg-primary'} />
        <div className="text-xs font-bold text-muted">
          {g.done} / {g.per_day}
        </div>
      </div>
    </Link>
  )
}
