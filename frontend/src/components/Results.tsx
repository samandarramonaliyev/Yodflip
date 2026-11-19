import { motion } from 'framer-motion'
import { BookmarkPlus, ChevronRight, Clock, Hand, Home, Layers, Plus, RotateCcw, Target, Zap } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { burst, feedbackWin } from '../lib/fx'
import { useMainButton } from '../lib/hooks'
import type { GameItem, Track } from '../games/types'
import { AddToDeckSheet } from './WordActions'
import { Spinner, toast } from './ui'

export function formatTime(ms: number) {
  const s = Math.round(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Full-width stacked buttons on phones, inline on desktop. */
export function ActionRow({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap [&>*]:w-full sm:[&>*]:w-auto sm:[&>*]:flex-1">{children}</div>
}

function StatGrid({ durationMs, flips, accuracy, xp, saving }: { durationMs: number; flips?: number; accuracy: number; xp: number | null; saving: boolean }) {
  const t = useT()
  const stats = [
    { icon: Clock, label: t('res.time'), value: formatTime(durationMs) },
    ...(flips !== undefined ? [{ icon: Hand, label: t('res.flips'), value: String(flips) }] : []),
    { icon: Target, label: t('res.accuracy'), value: `${accuracy}%` },
    { icon: Zap, label: 'XP', value: xp === null ? (saving ? '…' : '+0') : `+${xp}` },
  ]
  return (
    <div className={`mt-5 grid gap-2 ${stats.length === 4 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-3'}`}>
      {stats.map((s) => (
        <div key={s.label} className="rounded-2xl bg-line/60 p-3" data-testid={`stat-${s.label}`}>
          <s.icon className="mx-auto h-5 w-5 text-primary" />
          <div className="mt-1 text-xl font-black">{s.value}</div>
          <div className="text-xs font-bold text-muted">{s.label}</div>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------ between rounds */
export interface RoundCompleteProps {
  round: number // 0-based round that just finished
  total: number
  durationMs: number
  flips?: number
  accuracy: number
  xp: number | null
  saving: boolean
  onNext: () => void
}

export function RoundComplete({ round, total, durationMs, flips, accuracy, xp, saving, onNext }: RoundCompleteProps) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => burst(ref.current), [])
  useMainButton(t('res.next_round'), onNext)
  return (
    <motion.div ref={ref} initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto w-full max-w-xl space-y-4" data-testid="round-complete">
      <div className="card p-6 text-center">
        <div className="text-5xl">✅</div>
        <h2 className="h1 mt-2">{t('res.round_complete', { n: round + 1, total })}</h2>
        <StatGrid durationMs={durationMs} flips={flips} accuracy={accuracy} xp={xp} saving={saving} />
      </div>
      <ActionRow>
        <button className="btn-primary" onClick={onNext}>
          {t('res.next_round')} <ChevronRight className="h-5 w-5" />
        </button>
        <Link to="/" className="btn-ghost">
          <Home className="h-5 w-5" /> {t('res.home')}
        </Link>
      </ActionRow>
    </motion.div>
  )
}

/* ------------------------------------------------------------- final results */
export interface ResultsProps {
  track: Track
  durationMs: number
  flips?: number
  accuracy: number
  xp: number | null
  saving: boolean
  missed: GameItem[]
  newAchievements?: string[]
  learnedNow?: number
  /** Restart with the same word set, freshly shuffled */
  onNewGame: () => void
  /** "Boshqa to'plam" target (levels / sets / deck page) */
  otherSetTo?: string
  /** Extra content under the title (e.g. daily score) */
  extra?: ReactNode
  /** Extra buttons (e.g. "study missed again") */
  extraActions?: ReactNode
}

export function Results({
  track,
  durationMs,
  flips,
  accuracy,
  xp,
  saving,
  missed,
  newAchievements = [],
  learnedNow = 0,
  onNewGame,
  otherSetTo,
  extra,
  extraActions,
}: ResultsProps) {
  const t = useT()
  const [deckOpen, setDeckOpen] = useState(false)
  const [savedMissed, setSavedMissed] = useState(false)

  useEffect(() => {
    if (accuracy >= 60) feedbackWin()
    else burst(null)
  }, [accuracy])
  useMainButton(t('res.new_game'), onNewGame)

  const addMissedToWant = async () => {
    try {
      await api.post(
        '/words/lists/want/bulk/',
        missed.map((m) => ({ track, term: m.term, translation_uz: m.translation, definition: m.definition, article: m.article })),
      )
      setSavedMissed(true)
      toast.ok(t('lists.saved_want'))
    } catch {
      toast.err(t('err.generic'))
    }
  }

  return (
    <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto w-full max-w-xl space-y-4" data-testid="game-results">
      <div className="card p-6 text-center">
        <div className="text-6xl">{accuracy === 100 ? '🏆' : accuracy >= 70 ? '🎉' : accuracy >= 40 ? '💪' : '🌱'}</div>
        <h2 className="h1 mt-2">{accuracy === 100 ? t('res.perfect') : accuracy >= 70 ? t('res.great') : t('res.keep_going')}</h2>
        {extra}
        <StatGrid durationMs={durationMs} flips={flips} accuracy={accuracy} xp={xp} saving={saving} />
        {saving && (
          <div className="mt-3 flex items-center justify-center gap-2 text-sm text-muted">
            <Spinner className="h-4 w-4" /> {t('res.saving')}
          </div>
        )}
        {newAchievements.length > 0 && (
          <div className="mt-4 rounded-2xl bg-accent/25 p-3 font-bold">
            🏅 {t('res.new_badges')}: {newAchievements.map((c) => t(`ach.${c}`)).join(', ')}
          </div>
        )}
        {learnedNow > 0 && <div className="mt-3 rounded-2xl bg-success/15 p-3 text-sm font-bold text-success">✅ {t('res.learned_now', { n: learnedNow })}</div>}
      </div>

      {missed.length > 0 && (
        <div className="card p-4">
          <h3 className="h2 mb-2">
            {t('res.missed')} ({missed.length})
          </h3>
          <ul className="divide-y divide-line">
            {missed.map((m) => (
              <li key={m.key} className="py-2">
                <div className="font-extrabold">{m.term}</div>
                <div className="font-read text-sm text-muted">{m.translation || m.definition}</div>
              </li>
            ))}
          </ul>
          <button className="btn-ghost mt-3 w-full" onClick={() => setDeckOpen(true)}>
            <Plus className="h-5 w-5" /> {t('decks.add_to_deck')}
          </button>
          <AddToDeckSheet
            open={deckOpen}
            onClose={() => setDeckOpen(false)}
            track={track}
            words={missed.map((m) => ({ term: m.term, translation: m.translation, definition: m.definition, article: m.article }))}
          />
        </div>
      )}

      <ActionRow>
        <button className="btn-primary" onClick={onNewGame}>
          <RotateCcw className="h-5 w-5" /> {t('res.new_game')}
        </button>
        {otherSetTo && (
          <Link to={otherSetTo} className="btn-ghost">
            <Layers className="h-5 w-5" /> {t('res.other_set')}
          </Link>
        )}
        <Link to="/" className="btn-ghost">
          <Home className="h-5 w-5" /> {t('res.home')}
        </Link>
        {missed.length > 0 && (
          <button className="btn-soft" onClick={addMissedToWant} disabled={savedMissed}>
            <BookmarkPlus className="h-5 w-5" /> {savedMissed ? t('common.saved') : t('res.add_missed_want')}
          </button>
        )}
        {extraActions}
      </ActionRow>
    </motion.div>
  )
}
