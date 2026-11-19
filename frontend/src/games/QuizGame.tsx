import { AnimatePresence, motion } from 'framer-motion'
import { Timer } from 'lucide-react'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import { formatTime } from '../components/Results'
import { SpeakButton, WordActions } from '../components/WordActions'
import { ProgressBar } from '../components/ui'
import { useT } from '../i18n'
import { checkAnswer } from '../lib/fuzzy'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { useInterval } from '../lib/hooks'
import { sidesFor } from './direction'
import { makeOptions } from './quiz'
import { toResult, type GameProps, type ResultItem } from './types'

/**
 * Multiple-choice quiz (word → Uzbek, or reverse). Used by Review Mode and the Daily Challenge.
 * Falls back to typing when there aren't enough distractors.
 */
export default function QuizGame({ items, track, reverse, onFinish }: GameProps) {
  const t = useT()
  const [idx, setIdx] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const item = items[idx]
  const sides = sidesFor(item, 'review', track, reverse)
  const options = useMemo(() => makeOptions(item, items, 'review', track, reverse), [item, items, track, reverse])
  useInterval(() => setElapsed(Date.now() - start.current), 500)

  const answer = (value: string) => {
    if (picked !== null) return
    const ok = options ? value === sides.answer : checkAnswer(value, sides.answer) !== 'wrong'
    setPicked(value || ' ')
    results.current.push(toResult(item, ok))
    if (ok) feedbackCorrect()
    else feedbackWrong()
    setTimeout(
      () => {
        if (idx + 1 >= items.length) onFinish({ results: results.current, durationMs: Date.now() - start.current })
        else {
          setIdx((i) => i + 1)
          setPicked(null)
          setTyped('')
        }
      },
      ok ? 550 : 1500,
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    answer(typed)
  }

  const wasRight = picked !== null && (options ? picked === sides.answer : checkAnswer(picked, sides.answer) !== 'wrong')

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-center gap-3">
        <ProgressBar value={(idx / items.length) * 100} />
        <span className="chip shrink-0 bg-line text-sm">
          <Timer className="h-4 w-4" /> {formatTime(elapsed)}
        </span>
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={idx} initial={{ x: 30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -30, opacity: 0 }} transition={{ duration: 0.2 }} className="card space-y-2 p-6 text-center">
          <div className="text-xs font-black uppercase text-muted">
            {idx + 1} / {items.length}
          </div>
          <div className="flex items-center justify-center gap-2">
            <span className="break-words text-3xl font-black">{sides.prompt}</span>
            {sides.promptLang !== 'uz' && <SpeakButton text={sides.prompt} track={track} />}
          </div>
          {item.example && !reverse && <p className="font-read text-sm text-muted">“{item.example}”</p>}
        </motion.div>
      </AnimatePresence>

      {options ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {options.map((o) => {
            const st = picked !== null ? (o === sides.answer ? 'right' : o === picked ? 'wrong' : 'idle') : 'idle'
            return (
              <button
                key={o}
                onClick={() => answer(o)}
                className={`btn min-h-[58px] text-base ${st === 'right' ? 'bg-success text-white' : st === 'wrong' ? 'animate-shake bg-error text-white' : 'bg-card text-ink shadow-soft'}`}
              >
                {o}
              </button>
            )
          })}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-2">
          <input
            className={`input text-lg ${picked !== null ? (wasRight ? 'border-success' : 'animate-shake border-error') : ''}`}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={t('write.placeholder')}
            autoFocus
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
          />
          <button className="btn-primary w-full" disabled={picked !== null}>
            {t('common.check')}
          </button>
        </form>
      )}
      {picked !== null && !wasRight && (
        <div className="card flex items-center justify-between gap-2 p-3">
          <div>
            <div className="text-xs font-bold text-muted">{t('write.correct_answer')}</div>
            <div className="font-black text-success">{sides.answer}</div>
          </div>
          <WordActions word={item} track={track} />
        </div>
      )}
    </div>
  )
}
