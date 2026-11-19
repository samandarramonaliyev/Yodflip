import { AnimatePresence, motion } from 'framer-motion'
import { Maximize2 } from 'lucide-react'
import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { FlipCard } from '../components/FlipCard'
import { Sheet } from '../components/ui'
import { useT } from '../i18n'
import { burst, feedbackCorrect, feedbackWrong } from '../lib/fx'
import { haptic } from '../lib/telegram'
import { play } from '../lib/sound'
import { accuracy, createBoard, matchReducer, type MatchCard } from './matchMachine'
import { sidesFor } from './direction'
import { toResult, type GameProps } from './types'

const MISMATCH_MS = 1200
const LONG_TEXT = 70

function CardBack({ side }: { side: 'word' | 'def' }) {
  return (
    <div className={`grid h-full w-full place-items-center rounded-2xl shadow-soft ${side === 'word' ? 'bg-tint text-tint-ink' : 'bg-primary text-white'}`}>
      <span className="text-2xl font-black opacity-80">{side === 'word' ? 'W' : 'D'}</span>
    </div>
  )
}

function CardFront({ card, state, onExpand }: { card: MatchCard; state: 'open' | 'match' | 'miss'; onExpand: () => void }) {
  const long = card.side === 'def' && card.text.length > LONG_TEXT
  const ring = state === 'match' ? 'ring-4 ring-success bg-success/10' : state === 'miss' ? 'ring-4 ring-error bg-error/10' : 'ring-2 ring-primary/30'
  return (
    <div className={`relative flex h-full w-full items-center justify-center rounded-2xl bg-card p-2 text-center shadow-soft ${ring}`}>
      <span
        className={
          card.side === 'word'
            ? 'break-words text-[15px] font-black leading-tight sm:text-base'
            : 'font-read line-clamp-4 break-words text-[12.5px] leading-snug sm:text-sm'
        }
      >
        {card.text}
      </span>
      {long && (
        <button
          className="absolute bottom-1 right-1 grid h-7 w-7 place-items-center rounded-full bg-line text-muted"
          onClick={(e) => {
            e.stopPropagation()
            onExpand()
          }}
          aria-label="Expand"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

export default function MatchGame({ items, track, onFinish }: GameProps) {
  const t = useT()
  const pairs = useMemo(
    () =>
      items.map((i) => {
        const s = sidesFor(i, 'match', track)
        return { pairId: i.key, word: s.prompt, definition: s.answer }
      }),
    [items, track],
  )
  const [state, dispatch] = useReducer(matchReducer, pairs, (p) => createBoard(p))
  const [expanded, setExpanded] = useState<string | null>(null)
  const [celebrating, setCelebrating] = useState<string[]>([])
  const startRef = useRef<number | null>(null)
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const finished = useRef(false)

  // Feedback + mismatch timer
  useEffect(() => {
    if (state.lastEvent === 'match') {
      const last = state.log[state.log.length - 1]
      feedbackCorrect(cardRefs.current[`d-${last.pairId}`])
      const ids = [`w-${last.pairId}`, `d-${last.pairId}`]
      setCelebrating((c) => [...c, ...ids])
      const id = setTimeout(() => setCelebrating((c) => c.filter((x) => !ids.includes(x))), 550)
      return () => clearTimeout(id)
    } else if (state.lastEvent === 'miss') {
      feedbackWrong()
      const id = setTimeout(() => dispatch({ type: 'RESOLVE' }), MISMATCH_MS)
      return () => clearTimeout(id)
    }
  }, [state.lastEvent, state.log])

  // Round end
  useEffect(() => {
    if (state.phase !== 'done' || finished.current) return
    finished.current = true
    const byKey = new Map(items.map((i) => [i.key, i]))
    const durationMs = startRef.current ? Date.now() - startRef.current : 0
    const id = setTimeout(() => {
      burst(null, true)
      onFinish({
        results: state.log.map((l) => toResult(byKey.get(l.pairId)!, l.correct)),
        durationMs,
        flips: state.flips,
        misses: state.misses,
      })
    }, 650)
    return () => clearTimeout(id)
  }, [state.phase, state.log, state.flips, state.misses, items, onFinish])

  const flip = (c: MatchCard) => {
    if (state.phase !== 'idle' || c.faceUp || c.matched) return
    if ((c.side === 'word' && state.selectedWord) || (c.side === 'def' && state.selectedDef)) {
      haptic('select')
      return
    }
    startRef.current ??= Date.now()
    play('flip')
    haptic('light')
    dispatch({ type: 'FLIP', id: c.id })
  }

  const words = state.cards.filter((c) => c.side === 'word')
  const defs = state.cards.filter((c) => c.side === 'def')
  const n = pairs.length
  const wordCols = n <= 4 ? 'grid-cols-2 sm:grid-cols-4' : n <= 6 ? 'grid-cols-3 sm:grid-cols-6' : 'grid-cols-4 sm:grid-cols-4 lg:grid-cols-8'
  const defCols = n <= 4 ? 'grid-cols-2 sm:grid-cols-4' : n <= 6 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6' : 'grid-cols-2 sm:grid-cols-4'
  const missIds = state.phase === 'mismatch' ? [state.selectedWord, state.selectedDef] : []
  const expandedCard = state.cards.find((c) => c.id === expanded)

  const renderCard = (c: MatchCard, h: string) => {
    const st = c.matched ? 'match' : missIds.includes(c.id) ? 'miss' : 'open'
    return (
      <AnimatePresence key={c.id} mode="popLayout">
        {!c.matched || celebrating.includes(c.id) ? (
          <motion.div
            ref={(el) => (cardRefs.current[c.id] = el)}
            exit={{ scale: 0.6, opacity: 0, transition: { duration: 0.25 } }}
            animate={st === 'miss' ? { x: [0, -7, 7, -5, 5, 0] } : st === 'match' ? { scale: [1, 1.08, 1] } : {}}
            transition={{ duration: 0.4 }}
            className={h}
          >
            <button className="h-full w-full" onClick={() => flip(c)} aria-label={c.faceUp ? c.text : t('match.hidden_card')} aria-pressed={c.faceUp}>
              <FlipCard className="h-full w-full" flipped={c.faceUp} front={<CardBack side={c.side} />} back={<CardFront card={c} state={st} onExpand={() => setExpanded(c.id)} />} />
            </button>
          </motion.div>
        ) : (
          <div className={`${h} rounded-2xl border-2 border-dashed border-line`} aria-hidden />
        )}
      </AnimatePresence>
    )
  }

  return (
    <div className="mx-auto max-w-4xl select-none">
      <div className="mb-3 flex items-center justify-between gap-2 text-sm font-extrabold">
        <span className="chip bg-success/15 text-success">
          ✓ {state.matches}/{n}
        </span>
        <span className="chip bg-line text-muted">
          {t('res.flips')}: {state.flips}
        </span>
        <span className="chip bg-error/15 text-error">✗ {state.misses}</span>
        <span className="chip bg-primary-soft text-primary">{accuracy(state)}%</span>
      </div>

      <section aria-label={t('match.words')}>
        <div className="mb-1.5 text-xs font-black uppercase tracking-wide text-muted">{t('match.words')}</div>
        <div className={`grid gap-2 ${wordCols}`}>{words.map((c) => renderCard(c, 'h-[68px] sm:h-20'))}</div>
      </section>

      <div className="my-3 h-px bg-line" />

      <section aria-label={t('match.definitions')}>
        <div className="mb-1.5 text-xs font-black uppercase tracking-wide text-muted">{t('match.definitions')}</div>
        <div className={`grid gap-2 ${defCols}`}>{defs.map((c) => renderCard(c, 'h-[96px] sm:h-[110px]'))}</div>
      </section>

      <p className="mt-4 text-center text-sm text-muted">{t('match.hint')}</p>

      <Sheet open={Boolean(expandedCard)} onClose={() => setExpanded(null)} title={t('match.definition')}>
        <p className="font-read text-lg leading-relaxed">{expandedCard?.text}</p>
      </Sheet>
    </div>
  )
}
