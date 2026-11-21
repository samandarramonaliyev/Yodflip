import { FillerBadge } from '../components/LevelProgress'
import { motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FlipCard } from '../components/FlipCard'
import { useT } from '../i18n'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { play } from '../lib/sound'
import { sidesFor } from './direction'
import { shuffle } from './matchMachine'
import { toResult, type GameProps, type ResultItem } from './types'

interface MCard {
  id: string
  pair: string
  text: string
  lang: 'word' | 'uz'
  filler?: boolean
}

/** Extra game: classic concentration with word ↔ Uzbek cards mixed on one board. */
export default function MemoryPairs({ items, track, reverse, onFinish }: GameProps) {
  const t = useT()
  const set = items.slice(0, 6)
  const cards = useMemo<MCard[]>(
    () =>
      shuffle(
        set.flatMap((i) => {
          const s = sidesFor(i, 'memory', track, reverse)
          return [
            { id: `a-${i.key}`, pair: i.key, text: s.prompt, lang: s.promptLang === 'uz' ? 'uz' : 'word', filler: i.is_filler },
            { id: `b-${i.key}`, pair: i.key, text: s.answer, lang: s.answerLang === 'uz' ? 'uz' : 'word' },
          ] as MCard[]
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, track, reverse],
  )
  const [open, setOpen] = useState<string[]>([])
  const [matched, setMatched] = useState<string[]>([])
  const [bad, setBad] = useState(false)
  const [moves, setMoves] = useState(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef<number | null>(null)

  // Finish ~600ms after the last pair; refs keep the timer safe from parent re-renders.
  const finished = useRef(false)
  const onFinishRef = useRef(onFinish)
  onFinishRef.current = onFinish
  const movesRef = useRef(0)
  movesRef.current = moves
  const allMatched = matched.length > 0 && matched.length === set.length
  useEffect(() => {
    if (!allMatched) return
    const id = setTimeout(() => {
      if (finished.current) return
      finished.current = true
      onFinishRef.current({ results: results.current, durationMs: Date.now() - (start.current || Date.now()), flips: movesRef.current * 2 })
    }, 600)
    return () => clearTimeout(id)
  }, [allMatched])

  const tap = (c: MCard) => {
    if (open.length === 2 || open.includes(c.id) || matched.includes(c.pair)) return
    start.current ??= Date.now()
    play('flip')
    const next = [...open, c.id]
    setOpen(next)
    if (next.length < 2) return
    setMoves((m) => m + 1)
    const [a, b] = next.map((id) => cards.find((x) => x.id === id)!)
    const item = set.find((i) => i.key === a.pair)!
    if (a.pair === b.pair) {
      results.current.push(toResult(item, true))
      setTimeout(() => {
        setMatched((m) => [...m, a.pair])
        setOpen([])
        feedbackCorrect()
      }, 300)
    } else {
      results.current.push(toResult(item, false))
      setBad(true)
      feedbackWrong()
      setTimeout(() => {
        setOpen([])
        setBad(false)
      }, 1100)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-3">
      <div className="flex justify-between text-sm font-extrabold">
        <span className="chip bg-success/15 text-success">
          ✓ {matched.length}/{set.length}
        </span>
        <span className="chip bg-line text-muted">
          {t('memory.moves')}: {moves}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {cards.map((c) => {
          const isOpen = open.includes(c.id) || matched.includes(c.pair)
          const isMatched = matched.includes(c.pair)
          return (
            <motion.button
              key={c.id}
              onClick={() => tap(c)}
              animate={bad && open.includes(c.id) ? { x: [0, -6, 6, 0] } : isMatched ? { opacity: 0.55, scale: 0.96 } : {}}
              className="h-24 sm:h-28"
              aria-label={isOpen ? c.text : t('match.hidden_card')}
            >
              <FlipCard
                className="h-full w-full"
                flipped={isOpen}
                front={<div className={`grid h-full w-full place-items-center rounded-2xl text-2xl font-black shadow-soft ${c.lang === 'uz' ? 'bg-accent text-ink' : 'bg-tint text-tint-ink'}`}>?</div>}
                back={
                  <div className={`flex h-full w-full items-center justify-center rounded-2xl bg-card p-2 text-center shadow-soft ${isMatched ? 'ring-4 ring-success' : 'ring-2 ring-primary/30'}`}>
                    <span className="flex flex-col items-center gap-1 break-words text-sm font-extrabold leading-tight sm:text-base">
                      {c.filler && <FillerBadge />}
                      {c.text}
                    </span>
                  </div>
                }
              />
            </motion.button>
          )
        })}
      </div>
      <p className="text-center text-sm text-muted">{t('memory.hint')}</p>
    </div>
  )
}
