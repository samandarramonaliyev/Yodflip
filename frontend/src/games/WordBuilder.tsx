import { FillerBadge } from '../components/LevelProgress'
import { motion } from 'framer-motion'
import { Delete, Lightbulb, SkipForward } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { SpeakButton } from '../components/SpeakButton'
import { useT } from '../i18n'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { play } from '../lib/sound'
import { sidesFor } from './direction'
import { shuffle } from './matchMachine'
import { toResult, type GameProps, type ResultItem } from './types'

interface Tile {
  id: number
  ch: string
}

/** Default direction: Uzbek translation → build the foreign word. Reverse: word → build Uzbek. */
export default function WordBuilder({ items, track, reverse, onFinish }: GameProps) {
  const t = useT()
  const [idx, setIdx] = useState(0)
  const [placed, setPlaced] = useState<Tile[]>([])
  const [wrongTries, setWrongTries] = useState(0)
  const [status, setStatus] = useState<'play' | 'right' | 'wrong'>('play')
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const item = items[idx]
  // Builder flips the usual memorization direction so the default is Uzbek → word.
  const sides = sidesFor(item, 'builder', track, !reverse)
  const answer = sides.answer
  const letters = useMemo(() => answer.replace(/\s+/g, '').split(''), [answer])
  const tiles = useMemo<Tile[]>(() => shuffle(letters.map((ch, i) => ({ id: i, ch }))), [letters])
  const words = answer.split(/\s+/)
  const ref = useRef<HTMLDivElement>(null)

  const next = (correct: boolean) => {
    results.current.push(toResult(item, correct))
    setTimeout(() => {
      if (idx + 1 >= items.length) onFinish({ results: results.current, durationMs: Date.now() - start.current })
      else {
        setIdx(idx + 1)
        setPlaced([])
        setWrongTries(0)
        setStatus('play')
      }
    }, correct ? 700 : 1600)
  }

  useEffect(() => {
    if (status !== 'play' || placed.length !== letters.length) return
    const built = placed.map((p) => p.ch).join('')
    if (built.toLowerCase() === letters.join('').toLowerCase()) {
      setStatus('right')
      feedbackCorrect(ref.current)
      next(true)
    } else {
      feedbackWrong()
      if (wrongTries >= 1) {
        setStatus('wrong')
        next(false)
      } else {
        setWrongTries(1)
        setTimeout(() => setPlaced([]), 500)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed])

  const tap = (tile: Tile) => {
    if (status !== 'play' || placed.find((p) => p.id === tile.id)) return
    play('flip')
    setPlaced((p) => [...p, tile])
  }
  const hint = () => {
    if (status !== 'play') return
    const i = placed.length
    const correctPrefix = placed.every((p, k) => p.ch.toLowerCase() === letters[k].toLowerCase())
    const base = correctPrefix ? placed : []
    const need = letters[base.length]
    const tile = tiles.find((tl) => tl.ch === need && !base.find((p) => p.id === tl.id))
    if (tile) setPlaced([...base, tile])
    if (i === 0) setWrongTries(1) // a hint costs the free retry
  }

  // Render slots grouped by word
  let cursor = 0
  return (
    <div className="mx-auto max-w-xl space-y-5" ref={ref}>
      <div className="text-center text-sm font-extrabold text-muted">
        {idx + 1} / {items.length}
      </div>
      <div className="card flex min-h-[120px] items-center justify-center gap-3 p-6 text-center">
        {item.is_filler && <FillerBadge />}
        <span className="text-2xl font-black">{sides.prompt}</span>
        <SpeakButton text={sides.prompt} track={track} lang={sides.promptLang} />
      </div>

      <motion.div animate={status === 'wrong' || (wrongTries && placed.length === 0) ? { x: [0, -6, 6, 0] } : {}} className="flex flex-wrap justify-center gap-x-4 gap-y-2">
        {words.map((w, wi) => (
          <div key={wi} className="flex flex-wrap justify-center gap-1">
            {w.split('').map(() => {
              const k = cursor++
              const p = placed[k]
              const show = status === 'wrong' ? letters[k] : p?.ch
              return (
                <button
                  key={k}
                  onClick={() => status === 'play' && setPlaced((pl) => pl.slice(0, k))}
                  className={`grid h-11 w-9 place-items-center rounded-xl border-2 text-xl font-black sm:h-12 sm:w-10 ${
                    status === 'right' ? 'border-success bg-success/15 text-success' : status === 'wrong' ? 'border-error bg-error/10 text-error' : show ? 'border-primary bg-card' : 'border-dashed border-line'
                  }`}
                >
                  {show}
                </button>
              )
            })}
          </div>
        ))}
      </motion.div>

      <div className="flex flex-wrap justify-center gap-2">
        {tiles.map((tile) => {
          const used = Boolean(placed.find((p) => p.id === tile.id))
          return (
            <motion.button
              key={tile.id}
              whileTap={{ scale: 0.9 }}
              onClick={() => tap(tile)}
              disabled={used}
              className={`grid h-12 w-12 place-items-center rounded-2xl text-xl font-black shadow-soft transition ${used ? 'bg-line text-transparent shadow-none' : 'bg-tint text-tint-ink'}`}
            >
              {tile.ch}
            </motion.button>
          )
        })}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <button className="btn-ghost" onClick={() => setPlaced((p) => p.slice(0, -1))} disabled={!placed.length || status !== 'play'}>
          <Delete className="h-5 w-5" />
        </button>
        <button className="btn-ghost" onClick={hint} disabled={status !== 'play'}>
          <Lightbulb className="h-5 w-5" /> {t('builder.hint')}
        </button>
        <button
          className="btn-ghost"
          disabled={status !== 'play'}
          onClick={() => {
            setStatus('wrong')
            feedbackWrong()
            next(false)
          }}
        >
          <SkipForward className="h-5 w-5" />
        </button>
      </div>
      {wrongTries > 0 && status === 'play' && <p className="text-center text-sm font-bold text-error">{t('builder.try_again')}</p>}
    </div>
  )
}
