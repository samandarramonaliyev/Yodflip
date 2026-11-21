import { FillerBadge } from '../components/LevelProgress'
import { Heart } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useT } from '../i18n'
import { checkAnswer } from '../lib/fuzzy'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { sidesFor } from './direction'
import { shuffle } from './matchMachine'
import { toResult, type GameItem, type GameProps, type ResultItem } from './types'

interface Faller {
  uid: number
  item: GameItem
  x: number // 0..1
  y: number // 0..1 (1 = bottom)
  speed: number // fraction of height per second
}

const LIVES = 3

/** Uzbek translations fall; tap or type the matching word before they hit the bottom. Speed increases. */
export default function FallingWords({ items, track, reverse, onFinish }: GameProps) {
  const t = useT()
  const queue = useMemo(() => shuffle(items), [items])
  const [fallers, setFallers] = useState<Faller[]>([])
  const [lives, setLives] = useState(LIVES)
  const [score, setScore] = useState(0)
  const [text, setText] = useState('')
  const [flash, setFlash] = useState<'ok' | 'bad' | null>(null)
  const nextIdx = useRef(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const ended = useRef(false)
  const livesRef = useRef(LIVES)
  const uid = useRef(0)
  const fallersRef = useRef<Faller[]>([])
  const commit = () => setFallers([...fallersRef.current])

  // The falling text is the prompt; the player answers with the other side.
  // Default: Uzbek falls, answer is the foreign word.
  const sides = (i: GameItem) => sidesFor(i, 'falling', track, !reverse)

  const end = () => {
    if (ended.current) return
    ended.current = true
    onFinish({ results: results.current, durationMs: Date.now() - start.current })
  }

  // Spawner
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const spawn = () => {
      if (ended.current) return
      if (nextIdx.current < queue.length) {
        const n = nextIdx.current++
        const elapsed = (Date.now() - start.current) / 1000
        fallersRef.current.push({ uid: uid.current++, item: queue[n], x: 0.1 + Math.random() * 0.6, y: 0, speed: 0.07 + Math.min(0.13, elapsed * 0.0025) })
        commit()
      }
      const elapsed = (Date.now() - start.current) / 1000
      timer = setTimeout(spawn, Math.max(1400, 3600 - elapsed * 40))
    }
    spawn()
    return () => clearTimeout(timer)
  }, [queue])

  // Physics loop
  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const step = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (!ended.current && fallersRef.current.length) {
        const kept: Faller[] = []
        for (const f of fallersRef.current) {
          const y = f.y + f.speed * dt
          if (y >= 1) {
            results.current.push(toResult(f.item, false))
            livesRef.current -= 1
            setLives(livesRef.current)
            feedbackWrong()
          } else kept.push({ ...f, y })
        }
        fallersRef.current = kept
        commit()
      }
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [])

  useEffect(() => {
    if (lives <= 0) end()
    else if (nextIdx.current >= queue.length && fallers.length === 0 && results.current.length >= queue.length) end()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lives, fallers.length])

  const hit = (f: Faller) => {
    results.current.push(toResult(f.item, true))
    fallersRef.current = fallersRef.current.filter((x) => x.uid !== f.uid)
    commit()
    setScore((s) => s + 1)
    setFlash('ok')
    feedbackCorrect()
    setTimeout(() => setFlash(null), 250)
  }

  const tryAnswer = (value: string) => {
    const target = fallers
      .slice()
      .sort((a, b) => b.y - a.y)
      .find((f) => checkAnswer(value, sides(f.item).answer) !== 'wrong')
    if (target) hit(target)
    else {
      setFlash('bad')
      feedbackWrong()
      setTimeout(() => setFlash(null), 300)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    tryAnswer(text)
    setText('')
  }

  // Tap options: answers of current fallers + distractors, stable for the current set.
  const fallerKey = fallers.map((f) => f.uid).join(',')
  const options = useMemo(() => {
    const answers = fallers.map((f) => sides(f.item).answer)
    const distract = shuffle(items.map((i) => sides(i).answer).filter((a) => !answers.includes(a))).slice(0, Math.max(0, 4 - answers.length))
    return shuffle([...new Set([...answers, ...distract])]).slice(0, 6)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fallerKey])

  return (
    <div className="mx-auto max-w-xl select-none space-y-3">
      <div className="flex items-center justify-between">
        <span className="flex gap-1">
          {Array.from({ length: LIVES }).map((_, i) => (
            <Heart key={i} className={`h-6 w-6 ${i < lives ? 'fill-error text-error' : 'text-line'}`} />
          ))}
        </span>
        <span className="chip bg-primary-soft text-primary">
          {score} / {queue.length}
        </span>
      </div>
      <div className={`card relative h-[52vh] min-h-[300px] overflow-hidden transition ${flash === 'bad' ? 'ring-4 ring-error/50' : flash === 'ok' ? 'ring-4 ring-success/50' : ''}`}>
        {fallers.map((f) => (
          <div
            key={f.uid}
            className="absolute max-w-[70%] rounded-2xl bg-tint px-3 py-2 text-center text-base font-black text-tint-ink shadow-soft"
            style={{ left: `${f.x * 100}%`, top: `${f.y * 88}%`, transform: 'translateX(-20%)' }}
          >
            {f.item.is_filler && <FillerBadge className="mb-0.5 block w-fit" />}
            {sides(f.item).prompt}
          </div>
        ))}
        <div className="absolute inset-x-0 bottom-0 h-2 bg-error/40" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {options.map((o) => (
          <button key={o} className="btn-ghost min-h-[52px] text-base" onClick={() => tryAnswer(o)}>
            {o}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="flex gap-2">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('falling.type')} autoCapitalize="off" autoCorrect="off" spellCheck={false} />
        <button className="btn-primary">{t('common.ok')}</button>
      </form>
    </div>
  )
}
