import { motion } from 'framer-motion'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { ApiError } from '../lib/api'
import { duelApi, type AnswerResult, type Duel, type DuelQuestion } from '../lib/duel'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'

const REVEAL_MS = 500
const MIN_THINK_MS = 320 // the server rejects anything below 300 ms

interface Props {
  code: string
  mode: 'speed' | 'match'
  questions: DuelQuestion[]
  answered: number[]
  onDone: (d: Duel) => void
}

/** Plays the frozen questions of a duel. Right / wrong always comes from the server. */
export default function DuelBoard({ code, mode, questions, answered, onDone }: Props) {
  const t = useT()
  const [results, setResults] = useState<Record<number, AnswerResult>>(() =>
    Object.fromEntries(answered.map((i) => [i, { index: i, correct: false, correct_index: -1, answered: 0 }])),
  )
  const [busy, setBusy] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const shownAt = useRef(Date.now())
  const done = Object.keys(results).length >= questions.length
  const score = Object.values(results).filter((r) => r.correct).length

  const submit = useCallback(
    async (index: number, choice: number, el: HTMLElement | null): Promise<AnswerResult | null> => {
      const ms = Date.now() - shownAt.current
      if (ms < MIN_THINK_MS) return null
      setBusy(true)
      try {
        const r = await duelApi.answer(code, index, choice, ms)
        if (r.correct) feedbackCorrect(el)
        else feedbackWrong()
        return r
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return { index, correct: false, correct_index: -1, answered: 0 }
        if (!(e instanceof ApiError && e.status === 400)) toast.err(t('err.network'))
        return null
      } finally {
        setBusy(false)
      }
    },
    [code, t],
  )
  const commit = useCallback((r: AnswerResult) => {
    shownAt.current = Date.now()
    setResults((all) => ({ ...all, [r.index]: r }))
  }, [])

  const finish = useCallback(async () => {
    setFinishing(true)
    try {
      onDone(await duelApi.finish(code))
    } catch {
      toast.err(t('err.network'))
      setFinishing(false)
    }
  }, [code, onDone, t])
  const tried = useRef(false)
  useEffect(() => {
    if (!done || tried.current) return
    tried.current = true
    void finish()
  }, [done, finish])

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div className="flex items-center justify-between font-black">
        <span className="chip bg-line">⚔️ {Math.min(Object.keys(results).length + 1, questions.length)}/{questions.length}</span>
        <span className="chip bg-success/15 text-success">✓ {score}</span>
      </div>
      {done ? (
        <div className="grid place-items-center gap-3 py-16">
          {finishing ? (
            <Spinner className="h-8 w-8 text-primary" />
          ) : (
            <button className="btn-primary" onClick={() => void finish()}>
              {t('common.finish')}
            </button>
          )}
        </div>
      ) : mode === 'speed' ? (
        <SpeedRound questions={questions} results={results} busy={busy} submit={submit} commit={commit} />
      ) : (
        <MatchRound questions={questions} results={results} busy={busy} submit={submit} commit={commit} />
      )}
    </div>
  )
}

interface RoundProps {
  questions: DuelQuestion[]
  results: Record<number, AnswerResult>
  busy: boolean
  submit: (index: number, choice: number, el: HTMLElement | null) => Promise<AnswerResult | null>
  commit: (r: AnswerResult) => void
}

function SpeedRound({ questions, results, busy, submit, commit }: RoundProps) {
  const q = questions.find((x) => !(x.index in results))!
  const [reveal, setReveal] = useState<{ picked: number; correct: number } | null>(null)
  const choose = async (i: number, el: HTMLElement) => {
    if (busy || reveal) return
    const r = await submit(q.index, i, el)
    if (!r) return
    setReveal({ picked: i, correct: r.correct_index })
    setTimeout(() => {
      setReveal(null)
      commit(r)
    }, REVEAL_MS)
  }
  return (
    <>
      <motion.div key={q.index} initial={{ y: 12, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.18 }} className="card flex min-h-[140px] items-center justify-center p-6 text-center">
        <span className="break-words text-3xl font-black">{q.prompt}</span>
      </motion.div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {q.options.map((o, i) => {
          const st = reveal ? (i === reveal.correct ? 'right' : i === reveal.picked ? 'wrong' : 'idle') : 'idle'
          return (
            <button
              key={`${q.index}-${i}`}
              disabled={busy || Boolean(reveal)}
              onClick={(e) => void choose(i, e.currentTarget)}
              className={`btn min-h-[60px] text-lg ${st === 'right' ? 'bg-success text-white' : st === 'wrong' ? 'animate-shake bg-error text-white' : 'bg-card text-ink shadow-soft'}`}
            >
              {o}
            </button>
          )
        })}
      </div>
    </>
  )
}

/** Two boards of 5 words + 5 definitions (all open); every word has exactly one attempt. */
function MatchRound({ questions, results, busy, submit, commit }: RoundProps) {
  const t = useT()
  const board = questions.find((x) => !(x.index in results))!.board
  const qs = useMemo(() => questions.filter((x) => x.board === board), [questions, board])
  const [word, setWord] = useState<number | null>(null)
  const [def, setDef] = useState<number | null>(null)
  useEffect(() => {
    setWord(null)
    setDef(null)
  }, [board])
  const used = new Set(qs.map((x) => results[x.index]?.correct_index).filter((x) => x !== undefined))
  const attempt = async (w: number, d: number, el: HTMLElement | null) => {
    setWord(w)
    setDef(d)
    const r = await submit(w, d, el)
    setWord(null)
    setDef(null)
    if (r) commit(r)
  }
  return (
    <>
      <section>
        <div className="mb-1.5 text-xs font-black uppercase tracking-wide text-muted">{t('match.words')}</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {qs.map((x) => {
            const r = results[x.index]
            return (
              <button
                key={x.index}
                disabled={Boolean(r) || busy}
                aria-pressed={word === x.index}
                onClick={(e) => (def !== null ? void attempt(x.index, def, e.currentTarget) : setWord(x.index))}
                className={`min-h-[60px] break-words rounded-2xl p-2 font-black shadow-soft ${r ? (r.correct ? 'bg-success/20 text-success' : 'bg-error/15 text-error line-through') : word === x.index ? 'bg-primary text-white' : 'bg-tint text-tint-ink'}`}
              >
                {x.prompt}
              </button>
            )
          })}
        </div>
      </section>
      <section>
        <div className="mb-1.5 text-xs font-black uppercase tracking-wide text-muted">{t('match.definitions')}</div>
        <div className="grid gap-2">
          {qs[0].options.map((o, i) => (
            <button
              key={i}
              disabled={used.has(i) || busy}
              aria-pressed={def === i}
              onClick={(e) => (word !== null ? void attempt(word, i, e.currentTarget) : setDef(i))}
              className={`font-read min-h-[52px] rounded-2xl p-3 text-left text-sm shadow-soft transition ${used.has(i) ? 'bg-line/60 opacity-40' : def === i ? 'bg-primary text-white' : 'bg-card text-ink'}`}
            >
              {o}
            </button>
          ))}
        </div>
      </section>
      <p className="text-center text-sm text-muted">{t('duel.match_hint')}</p>
    </>
  )
}
