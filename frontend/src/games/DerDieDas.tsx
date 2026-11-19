import { motion, useAnimationControls, type PanInfo } from 'framer-motion'
import { Heart } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useT } from '../i18n'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { shuffle } from './matchMachine'
import { toResult, type GameProps, type ResultItem } from './types'

const ARTICLES = [
  { a: 'der', cls: 'bg-sky-500', key: '1', hint: '←' },
  { a: 'die', cls: 'bg-error', key: '2', hint: '↓' },
  { a: 'das', cls: 'bg-success', key: '3', hint: '→' },
] as const

const LIVES = 3

/** German nouns drop down; pick the article by tap, keys 1/2/3 or swipe (← der, ↓ die, → das). */
export default function DerDieDas({ items, track, onFinish }: GameProps) {
  const t = useT()
  const order = useMemo(() => shuffle(items), [items])
  const [idx, setIdx] = useState(0)
  const [lives, setLives] = useState(LIVES)
  const [feedback, setFeedback] = useState<{ ok: boolean; answer: string } | null>(null)
  const [score, setScore] = useState(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const controls = useAnimationControls()
  const busy = useRef(false)
  const item = order[idx]
  const dropMs = Math.max(2600, 6000 - idx * 120)

  const end = useCallback(() => onFinish({ results: results.current, durationMs: Date.now() - start.current }), [onFinish])

  const answer = useCallback(
    (a: string | null) => {
      if (busy.current || !item) return
      busy.current = true
      controls.stop()
      const ok = a === item.article
      results.current.push(toResult(item, ok))
      setFeedback({ ok, answer: item.article })
      let newLives = lives
      if (ok) {
        setScore((s) => s + 1)
        feedbackCorrect()
      } else {
        feedbackWrong()
        newLives = lives - 1
        setLives(newLives)
      }
      setTimeout(
        () => {
          setFeedback(null)
          busy.current = false
          if (newLives <= 0 || idx + 1 >= order.length) end()
          else setIdx((i) => i + 1)
        },
        ok ? 450 : 1100,
      )
    },
    [item, lives, idx, order.length, end, controls],
  )

  useEffect(() => {
    if (!item) return
    controls.set({ y: 0, x: 0, opacity: 1 })
    void controls.start({ y: 300, transition: { duration: dropMs / 1000, ease: 'linear' } }).then(() => {
      if (!busy.current) answer(null) // reached the bottom
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const found = ARTICLES.find((x) => x.key === e.key)
      if (found) answer(found.a)
      if (e.key === 'ArrowLeft') answer('der')
      if (e.key === 'ArrowDown') answer('die')
      if (e.key === 'ArrowRight') answer('das')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [answer])

  const onPanEnd = (_: unknown, info: PanInfo) => {
    const { x, y } = info.offset
    if (Math.abs(x) > 60 && Math.abs(x) > Math.abs(y)) answer(x < 0 ? 'der' : 'das')
    else if (y > 60) answer('die')
  }

  if (track !== 'de' || !item) return null

  return (
    <div className="mx-auto max-w-md select-none space-y-4">
      <div className="flex items-center justify-between">
        <span className="flex gap-1" aria-label={`${lives} lives`}>
          {Array.from({ length: LIVES }).map((_, i) => (
            <Heart key={i} className={`h-6 w-6 ${i < lives ? 'fill-error text-error' : 'text-line'}`} />
          ))}
        </span>
        <span className="chip bg-primary-soft text-primary">
          {score} · {idx + 1}/{order.length}
        </span>
      </div>

      <div className="card relative h-[380px] touch-none overflow-hidden" onPointerDown={() => undefined}>
        <motion.div
          animate={controls}
          drag
          dragSnapToOrigin
          dragElastic={0.6}
          onPanEnd={onPanEnd}
          className={`absolute left-1/2 top-4 -ml-[110px] flex w-[220px] cursor-grab flex-col items-center rounded-2xl px-4 py-5 text-center shadow-lift ${
            feedback ? (feedback.ok ? 'bg-success text-white' : 'bg-error text-white') : 'bg-tint text-tint-ink'
          }`}
        >
          <span className="text-2xl font-black">
            {feedback ? `${feedback.answer} ` : ''}
            {item.word}
          </span>
          <span className="mt-1 text-sm opacity-80">{item.translation}</span>
        </motion.div>
        <div className="absolute inset-x-0 bottom-0 h-2 bg-error/40" />
      </div>

      <div className="grid grid-cols-3 gap-2">
        {ARTICLES.map((x) => (
          <button key={x.a} onClick={() => answer(x.a)} className={`btn min-h-[64px] flex-col gap-0 text-xl text-white ${x.cls}`}>
            {x.a}
            <span className="text-xs opacity-70">{x.hint}</span>
          </button>
        ))}
      </div>
      <p className="text-center text-sm text-muted">{t('dds.hint')}</p>
    </div>
  )
}
