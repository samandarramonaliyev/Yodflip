import { FillerBadge } from '../components/LevelProgress'
import { AnimatePresence, motion } from 'framer-motion'
import { Timer, Zap } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { SpeakButton } from '../components/SpeakButton'
import { useT } from '../i18n'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { useInterval } from '../lib/hooks'
import { play } from '../lib/sound'
import { usePreload } from '../lib/tts'
import { sidesFor } from './direction'
import { shuffle } from './matchMachine'
import { makeOptions } from './quiz'
import { toResult, type GameProps, type ResultItem } from './types'

const DURATION = 60

export function comboMultiplier(combo: number) {
  return Math.min(4, 1 + Math.floor(combo / 3))
}

export default function SpeedMatch({ items, track, reverse, onFinish }: GameProps) {
  const t = useT()
  const order = useMemo(() => shuffle(items), [items])
  const [idx, setIdx] = useState(0)
  const [left, setLeft] = useState(DURATION)
  const [started, setStarted] = useState(false)
  const [combo, setCombo] = useState(0)
  const [score, setScore] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const results = useRef<ResultItem[]>([])
  const comboMax = useRef(0)
  const done = useRef(false)
  const startedAt = useRef(0)

  const item = order[idx % order.length]
  usePreload([item.term, order[(idx + 1) % order.length]?.term], track)
  const sides = sidesFor(item, 'speed', track, reverse)
  const options = useMemo(() => makeOptions(item, items, 'speed', track, reverse) ?? [sides.answer], [item, items, track, reverse, sides.answer])

  const finish = () => {
    if (done.current) return
    done.current = true
    onFinish({ results: results.current, durationMs: Date.now() - startedAt.current, comboMax: comboMax.current })
  }

  useInterval(
    () => {
      if (left <= 1) {
        setLeft(0)
        finish()
        return
      }
      if (left <= 6) play('tick')
      setLeft(left - 1)
    },
    started && left > 0 ? 1000 : null,
  )

  const choose = (opt: string, el: HTMLElement) => {
    if (picked || left <= 0) return
    if (!started) {
      setStarted(true)
      startedAt.current = Date.now()
    }
    const correct = opt === sides.answer
    setPicked(opt)
    results.current.push(toResult(item, correct))
    if (correct) {
      const c = combo + 1
      setCombo(c)
      comboMax.current = Math.max(comboMax.current, c)
      setScore((s) => s + 10 * comboMultiplier(c))
      feedbackCorrect(el)
    } else {
      setCombo(0)
      feedbackWrong()
    }
    setTimeout(
      () => {
        setPicked(null)
        setIdx((i) => i + 1)
      },
      correct ? 250 : 700,
    )
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div className="flex items-center justify-between">
        <span className={`chip text-base ${left <= 10 ? 'bg-error/15 text-error' : 'bg-line'}`}>
          <Timer className="h-5 w-5" /> {left}s
        </span>
        <span className="chip bg-accent/30 text-base">
          <Zap className="h-5 w-5" /> x{comboMultiplier(combo)} · {combo}
        </span>
        <span className="chip bg-primary-soft text-base text-primary">{score}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <motion.div className="h-full bg-primary" animate={{ width: `${(left / DURATION) * 100}%` }} transition={{ duration: 0.3 }} />
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={idx} initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -16, opacity: 0 }} transition={{ duration: 0.18 }} className="card flex min-h-[140px] items-center justify-center gap-3 p-6 text-center">
          {item.is_filler && <FillerBadge />}
          <span className="break-words text-3xl font-black">{sides.prompt}</span>
          <SpeakButton text={sides.prompt} track={track} lang={sides.promptLang} />
        </motion.div>
      </AnimatePresence>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {options.map((o) => {
          const state = picked ? (o === sides.answer ? 'right' : o === picked ? 'wrong' : 'idle') : 'idle'
          return (
            <button
              key={o}
              onClick={(e) => choose(o, e.currentTarget)}
              className={`btn min-h-[60px] text-lg ${
                state === 'right' ? 'bg-success text-white' : state === 'wrong' ? 'animate-shake bg-error text-white' : 'bg-card text-ink shadow-soft'
              }`}
            >
              {o}
            </button>
          )
        })}
      </div>
      {!started && <p className="text-center text-sm text-muted">{t('speed.hint')}</p>}
      {started && (
        <button className="mx-auto block text-sm font-bold text-muted underline" onClick={finish}>
          {t('common.finish')}
        </button>
      )}
    </div>
  )
}
