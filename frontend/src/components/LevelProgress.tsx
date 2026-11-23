import { motion } from 'framer-motion'
import { ChevronRight, RotateCcw } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useT } from '../i18n'
import { burst } from '../lib/fx'
import type { LevelProgress } from '../lib/types'
import { useApp } from '../store/app'

const NEXT: Record<string, string | undefined> = { A1: 'A2', A2: 'B1', B1: 'B2', B2: 'C1', C1: undefined }

/** Small "takror" badge on review-filler cards (found words that only fill the board). */
export function FillerBadge({ className = '' }: { className?: string }) {
  const t = useT()
  return (
    <span className={`inline-flex items-center rounded-full bg-accent/35 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-ink ${className}`} data-testid="filler-badge">
      🔁 {t('level.filler')}
    </span>
  )
}

/** "37 / 100 so'z" + bar + % (optionally animated from a previous value). */
export function LevelBar({ progress, from }: { progress: LevelProgress; from?: number }) {
  const t = useT()
  const color = progress.completed ? 'bg-success' : progress.to_unlock === 0 ? 'bg-success' : 'bg-primary'
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-sm font-bold">
        <span data-testid="level-count">{t('level.count', { n: progress.found, total: progress.total })}</span>
        <span className="text-primary">{progress.percent}%</span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}>
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: `${from ?? 0}%` }}
          animate={{ width: `${Math.min(100, progress.percent)}%` }}
          transition={{ duration: 0.9, ease: 'easeOut', delay: 0.15 }}
        />
      </div>
    </div>
  )
}

export function unlockText(t: (k: string, v?: Record<string, string | number>) => string, p: LevelProgress): string {
  if (p.exam) return p.completed ? t('exam.completed') : t('level.remaining', { n: p.remaining })
  if (p.completed) return t('level.completed_short')
  if (p.to_unlock > 0) return t('level.to_unlock', { n: p.to_unlock })
  return NEXT[p.level] ? t('level.next_open') : t('level.remaining', { n: p.remaining })
}

/** Results-screen panel of a level round: +N new words, animated bar, words left to unlock. */
export function LevelRoundSummary({ before, after, newFound }: { before: LevelProgress; after: LevelProgress | null; newFound: number | null }) {
  const t = useT()
  const lang = useApp((s) => s.lang)
  const shown = after ?? before
  const justUnlocked = Boolean(after && before.to_unlock > 0 && after.to_unlock === 0 && NEXT[after.level])
  return (
    <div className="mt-4 space-y-3 rounded-2xl bg-line/50 p-4 text-left" data-testid="level-summary">
      <div className="flex items-center justify-between gap-2">
        <span className="font-black">
          {before.exam ? `📘 ${before.name?.[lang] ?? ''}` : `${before.level} · ${t(`cefr.${before.level}`)}`}
        </span>
        <span className={`rounded-full px-3 py-1 text-sm font-black ${newFound ? 'bg-success/20 text-success' : 'bg-line text-muted'}`} data-testid="new-found">
          {newFound === null ? '…' : newFound > 0 ? t('level.new_found', { n: newFound }) : t('level.no_new')}
        </span>
      </div>
      <LevelBar progress={shown} from={before.percent} />
      <p className="text-sm font-bold text-muted" data-testid="unlock-text">
        {unlockText(t, shown)}
      </p>
      {justUnlocked && (
        <Link to={`/levels/${NEXT[shown.level]}`} className="btn-soft w-full">
          🔓 {t('level.unlocked_now', { level: NEXT[shown.level]! })}
        </Link>
      )}
    </div>
  )
}

/** A whole exam pack is found. */
export function ExamComplete({ slug }: { slug: string }) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => burst(ref.current), [])
  return (
    <div ref={ref} className="card space-y-4 p-6 text-center" data-testid="exam-complete">
      <div className="text-6xl">🎖️</div>
      <h2 className="h1">{t('exam.completed')}</h2>
      <div className="grid gap-2">
        <Link to={`/exams/${slug}/simulation`} className="btn-primary">
          {t('exam.simulation')} <ChevronRight className="h-5 w-5" />
        </Link>
        <Link to={`/exams/${slug}`} className="btn-ghost">
          {t('exam.back_to_pack')}
        </Link>
      </div>
    </div>
  )
}

/** "Daraja yakunlandi 🎉" — badge, one-time bonus XP, next level and a review session. */
export function LevelComplete({ level, bonusXp }: { level: string; bonusXp: number }) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => burst(ref.current), [])
  const next = NEXT[level]
  return (
    <motion.div ref={ref} initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="card space-y-4 p-6 text-center" data-testid="level-complete">
      <div className="text-6xl">🎓</div>
      <h2 className="h1">{t('level.complete_title')}</h2>
      <p className="text-muted">{t('level.complete_text', { level })}</p>
      {bonusXp > 0 && <div className="rounded-2xl bg-accent/25 p-3 font-black">🏅 {t('ach.level_complete')} · +{bonusXp} XP</div>}
      <div className="grid gap-2">
        {next && (
          <Link to={`/levels/${next}`} className="btn-primary">
            {t('level.go_next', { level: next })} <ChevronRight className="h-5 w-5" />
          </Link>
        )}
        <Link to={`/play/speed?source=levelreview&level=${level}`} className="btn-ghost">
          <RotateCcw className="h-5 w-5" /> {t('level.review')}
        </Link>
      </div>
    </motion.div>
  )
}
