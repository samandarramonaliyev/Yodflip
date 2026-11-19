import { motion } from 'framer-motion'
import { BookmarkPlus, ChevronRight, Clock, Hand, Plus, RotateCcw, Target, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { feedbackWin } from '../lib/fx'
import type { ResultsResponse } from '../lib/types'
import type { GameItem, Track } from '../games/types'
import { AddToDeckSheet } from './WordActions'
import { Spinner, toast } from './ui'

export interface ResultsProps {
  track: Track
  durationMs: number
  flips?: number
  accuracy: number
  missed: GameItem[]
  server: ResultsResponse | null
  saving: boolean
  onReplay: () => void
  onNext?: () => void
  nextLabel?: string
  extra?: React.ReactNode
}

export function formatTime(ms: number) {
  const s = Math.round(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function Results({ track, durationMs, flips, accuracy, missed, server, saving, onReplay, onNext, nextLabel, extra }: ResultsProps) {
  const t = useT()
  const [deckOpen, setDeckOpen] = useState(false)
  const [savedMissed, setSavedMissed] = useState(false)

  useEffect(() => {
    if (accuracy >= 60) feedbackWin()
  }, [accuracy])

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

  const stats = [
    { icon: Clock, label: t('res.time'), value: formatTime(durationMs) },
    ...(flips !== undefined ? [{ icon: Hand, label: t('res.flips'), value: String(flips) }] : []),
    { icon: Target, label: t('res.accuracy'), value: `${accuracy}%` },
    { icon: Zap, label: 'XP', value: saving ? '…' : `+${server?.xp_earned ?? 0}` },
  ]

  return (
    <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto w-full max-w-xl space-y-4">
      <div className="card p-6 text-center">
        <div className="text-6xl">{accuracy === 100 ? '🏆' : accuracy >= 70 ? '🎉' : accuracy >= 40 ? '💪' : '🌱'}</div>
        <h2 className="h1 mt-2">{accuracy === 100 ? t('res.perfect') : accuracy >= 70 ? t('res.great') : t('res.keep_going')}</h2>
        {extra}
        <div className={`mt-5 grid gap-2 ${stats.length === 4 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-3'}`}>
          {stats.map((s) => (
            <div key={s.label} className="rounded-2xl bg-line/60 p-3">
              <s.icon className="mx-auto h-5 w-5 text-primary" />
              <div className="mt-1 text-xl font-black">{s.value}</div>
              <div className="text-xs font-bold text-muted">{s.label}</div>
            </div>
          ))}
        </div>
        {saving && (
          <div className="mt-3 flex items-center justify-center gap-2 text-sm text-muted">
            <Spinner className="h-4 w-4" /> {t('res.saving')}
          </div>
        )}
        {server?.new_achievements?.length ? (
          <div className="mt-4 rounded-2xl bg-accent/25 p-3 font-bold">
            🏅 {t('res.new_badges')}: {server.new_achievements.map((c) => t(`ach.${c}`)).join(', ')}
          </div>
        ) : null}
        {server?.learned_now?.length ? (
          <div className="mt-3 rounded-2xl bg-success/15 p-3 text-sm font-bold text-success">
            ✅ {t('res.learned_now', { n: server.learned_now.length })}
          </div>
        ) : null}
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
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <button className="btn-soft" onClick={addMissedToWant} disabled={savedMissed}>
              <BookmarkPlus className="h-5 w-5" /> {savedMissed ? t('common.saved') : t('res.add_missed_want')}
            </button>
            <button className="btn-ghost" onClick={() => setDeckOpen(true)}>
              <Plus className="h-5 w-5" /> {t('decks.add_to_deck')}
            </button>
          </div>
          <AddToDeckSheet
            open={deckOpen}
            onClose={() => setDeckOpen(false)}
            track={track}
            words={missed.map((m) => ({ term: m.term, translation: m.translation, definition: m.definition, article: m.article }))}
          />
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <button className="btn-ghost" onClick={onReplay}>
          <RotateCcw className="h-5 w-5" /> {t('res.replay')}
        </button>
        {onNext && (
          <button className="btn-primary" onClick={onNext}>
            {nextLabel || t('res.next_round')} <ChevronRight className="h-5 w-5" />
          </button>
        )}
      </div>
    </motion.div>
  )
}
