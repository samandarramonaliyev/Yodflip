import { AnimatePresence, motion, type PanInfo } from 'framer-motion'
import { ArrowLeft, ArrowLeftRight, Check, RotateCcw, X } from 'lucide-react'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FlipCard } from '../components/FlipCard'
import { Results } from '../components/Results'
import { SpeakButton } from '../components/WordActions'
import { EmptyState, ErrorState, ListSkeleton, ProgressBar } from '../components/ui'
import { sidesFor } from '../games/direction'
import { shuffle } from '../games/matchMachine'
import { makeOptions } from '../games/quiz'
import { toResult, type GameId, type GameItem, type GameOutcome, type ResultItem, type Track } from '../games/types'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { checkAnswer } from '../lib/fuzzy'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { useAsync, useTelegramBack } from '../lib/hooks'
import { haptic } from '../lib/telegram'
import type { Card, Deck, ResultsResponse } from '../lib/types'
import { useApp } from '../store/app'

export function cardToItem(c: Card, lang: GameItem['translation_lang'] = 'uz'): GameItem {
  const parts = c.term.split(/\s+/)
  let word = c.term
  let article = c.article
  if (parts.length > 1 && ['der', 'die', 'das'].includes(parts[0].toLowerCase())) {
    article = parts[0].toLowerCase()
    word = parts.slice(1).join(' ')
  }
  return {
    key: `c${c.id}`,
    word_id: null,
    term: article ? `${article} ${word}` : word,
    word,
    article,
    definition: c.definition,
    translation: c.translation,
    pos: '',
    example: c.example,
    example_uz: '',
    translation_lang: lang,
  }
}

type StudyMode = 'flashcards' | 'learn' | 'write'

interface StudyProps {
  items: GameItem[]
  track: Track
  reverse: boolean
  onFinish: (o: GameOutcome) => void
}

export default function DeckStudy() {
  const { id, mode = 'flashcards' } = useParams<{ id: string; mode: StudyMode }>()
  const t = useT()
  const nav = useNavigate()
  useTelegramBack(`/decks/${id}`)
  const bumpUser = useApp((s) => s.bumpUser)
  const { data: deck, error, loading, reload } = useAsync(() => api.get<Deck>(`/decks/${id}/`), [id])
  const [reverse, setReverse] = useState(false)
  const [round, setRound] = useState(0)
  const [outcome, setOutcome] = useState<GameOutcome | null>(null)
  const [server, setServer] = useState<ResultsResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [subset, setSubset] = useState<GameItem[] | null>(null)
  const savedRounds = useRef(new Set<number>())
  const items = useMemo(() => (deck?.cards || []).map((c) => cardToItem(c, deck?.translation_lang ?? 'uz')).filter((i) => i.translation), [deck])

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>
  if (loading || !deck) return <div className="page"><ListSkeleton rows={3} height="h-40" /></div>
  if (!items.length) return <div className="page"><EmptyState emoji="🃏" title={t('decks.no_cards')} /></div>

  const finish = async (o: GameOutcome) => {
    if (savedRounds.current.has(round)) return // each study run is saved exactly once
    savedRounds.current.add(round)
    setOutcome(o)
    setSaving(true)
    setServer(null)
    try {
      const r = await api.post<ResultsResponse>('/games/results/', {
        game: mode as GameId,
        track: deck.track,
        source: 'deck',
        results: o.results,
        duration_ms: Math.round(o.durationMs),
      })
      setServer(r)
      bumpUser({ xp: r.xp_total, streak: r.streak, level: r.level })
    } catch {
      /* local results still shown */
    } finally {
      setSaving(false)
    }
  }

  const playItems = subset || items
  const Comp = mode === 'learn' ? Learn : mode === 'write' ? Write : Flashcards
  const wrong = outcome ? new Set(outcome.results.filter((r) => !r.correct).map((r) => r.term)) : new Set<string>()
  const missed = playItems.filter((i) => wrong.has(i.term))
  const accuracy = outcome?.results.length ? Math.round((100 * outcome.results.filter((r) => r.correct).length) / outcome.results.length) : 0

  return (
    <div className="mx-auto w-full max-w-3xl px-3 pb-10 pt-3">
      <div className="mb-3 flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav(`/decks/${deck.id}`)} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate font-black">{deck.name}</div>
          <div className="text-xs font-bold text-muted">{t(`study.${mode}`)}</div>
        </div>
        <button
          className={`chip ${reverse ? 'bg-primary text-white' : 'bg-line'}`}
          onClick={() => {
            setReverse((r) => !r)
            setRound((r) => r + 1)
            setOutcome(null)
          }}
          aria-pressed={reverse}
        >
          <ArrowLeftRight className="h-4 w-4" /> {reverse ? 'UZ → ' + deck.track.toUpperCase() : deck.track.toUpperCase() + ' → UZ'}
        </button>
      </div>
      {outcome ? (
        <Results
          track={deck.track}
          durationMs={outcome.durationMs}
          accuracy={accuracy}
          missed={missed}
          xp={server ? server.xp_earned : null}
          saving={saving}
          newAchievements={server?.new_achievements}
          learnedNow={server?.learned_now.length}
          onNewGame={() => {
            setSubset(null)
            setOutcome(null)
            setRound((r) => r + 1)
            window.scrollTo({ top: 0 })
          }}
          otherSetTo="/decks"
          extraActions={
            missed.length ? (
              <button
                className="btn-ghost"
                onClick={() => {
                  setSubset(missed)
                  setOutcome(null)
                  setRound((r) => r + 1)
                }}
              >
                🔁 {t('study.again_missed')}
              </button>
            ) : null
          }
        />
      ) : (
        <Comp key={`${round}-${mode}`} items={playItems} track={deck.track} reverse={reverse} onFinish={finish} />
      )}
    </div>
  )
}

/* ------------------------------------------------------------- Flashcards */
function Flashcards({ items, track, reverse, onFinish }: StudyProps) {
  const t = useT()
  const order = useMemo(() => shuffle(items), [items])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [exitDir, setExitDir] = useState(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const item = order[idx]
  const s = sidesFor(item, 'flashcards', track, reverse)

  const answer = (know: boolean) => {
    haptic(know ? 'success' : 'light')
    results.current.push(toResult(item, know))
    setExitDir(know ? 1 : -1)
    setTimeout(() => {
      if (idx + 1 >= order.length) onFinish({ results: results.current, durationMs: Date.now() - start.current })
      else {
        setIdx(idx + 1)
        setFlipped(false)
        setExitDir(0)
      }
    }, 180)
  }

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.x > 90) answer(true)
    else if (info.offset.x < -90) answer(false)
  }

  const face = (text: string, lang: string, sub?: string) => (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-[24px] bg-card p-6 text-center shadow-lift">
      <span className="break-words text-3xl font-black">{text}</span>
      {sub && <span className="font-read text-sm text-muted">{sub}</span>}
      <SpeakButton text={text} track={track} lang={lang} />
    </div>
  )

  return (
    <div className="space-y-4">
      <ProgressBar value={(idx / order.length) * 100} />
      <div className="text-center text-sm font-bold text-muted">
        {idx + 1} / {order.length}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={idx}
          drag="x"
          dragSnapToOrigin
          onDragEnd={onDragEnd}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1, x: 0 }}
          exit={{ opacity: 0, x: exitDir * 260, rotate: exitDir * 12 }}
          transition={{ duration: 0.2 }}
          className="mx-auto h-[340px] max-w-md cursor-grab touch-pan-y"
          onClick={() => setFlipped((f) => !f)}
        >
          <FlipCard className="h-full w-full" flipped={flipped} front={face(s.prompt, s.promptLang)} back={face(s.answer, s.answerLang, item.definition && !reverse ? item.definition : undefined)} />
        </motion.div>
      </AnimatePresence>
      <p className="text-center text-sm text-muted">{t('study.flash_hint')}</p>
      <div className="mx-auto grid max-w-md grid-cols-2 gap-3">
        <button className="btn bg-error/15 text-error" onClick={() => answer(false)}>
          <X className="h-5 w-5" /> {t('study.still_learning')}
        </button>
        <button className="btn bg-success text-white" onClick={() => answer(true)}>
          <Check className="h-5 w-5" /> {t('study.know')}
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Learn */
interface LearnEntry {
  item: GameItem
  stage: 0 | 1 // 0 = multiple choice, 1 = typing
}

function Learn({ items, track, reverse, onFinish }: StudyProps) {
  const t = useT()
  const [queue, setQueue] = useState<LearnEntry[]>(() => shuffle(items).map((item) => ({ item, stage: 0 as const })))
  const [picked, setPicked] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const [mastered, setMastered] = useState(0)
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const cur = queue[0]
  const s = sidesFor(cur.item, 'learn', track, reverse)
  const options = useMemo(() => (cur.stage === 0 ? makeOptions(cur.item, items, 'learn', track, reverse) : null), [cur, items, track, reverse])
  const stage = options ? cur.stage : 1

  const advance = (ok: boolean) => {
    results.current.push(toResult(cur.item, ok))
    setTimeout(
      () => {
        setPicked(null)
        setTyped('')
        const rest = queue.slice(1)
        let next: LearnEntry[]
        if (ok && stage === 1) {
          setMastered((m) => m + 1)
          next = rest
        } else if (ok) {
          next = [...rest.slice(0, 2), { item: cur.item, stage: 1 }, ...rest.slice(2)]
        } else {
          // Adapt to mistakes: back to multiple choice, comes back soon.
          next = [...rest.slice(0, 2), { item: cur.item, stage: 0 }, ...rest.slice(2)]
        }
        if (!next.length) onFinish({ results: results.current, durationMs: Date.now() - start.current })
        else setQueue(next)
      },
      ok ? 500 : 1500,
    )
  }

  const choose = (o: string) => {
    if (picked !== null) return
    setPicked(o)
    const ok = o === s.answer
    if (ok) feedbackCorrect()
    else feedbackWrong()
    advance(ok)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (picked !== null) return
    const v = checkAnswer(typed, s.answer)
    setPicked(typed || ' ')
    if (v !== 'wrong') feedbackCorrect()
    else feedbackWrong()
    advance(v !== 'wrong')
  }
  const typedOk = picked !== null && checkAnswer(picked, s.answer) !== 'wrong'

  return (
    <div className="space-y-4">
      <ProgressBar value={(mastered / items.length) * 100} color="bg-success" />
      <div className="text-center text-sm font-bold text-muted">{t('study.mastered', { n: mastered, total: items.length })}</div>
      <div className="card space-y-2 p-6 text-center">
        <div className="text-xs font-black uppercase text-muted">{stage === 0 ? t('study.choose') : t('study.type')}</div>
        <div className="flex items-center justify-center gap-2">
          <span className="break-words text-3xl font-black">{s.prompt}</span>
          <SpeakButton text={s.prompt} track={track} lang={s.promptLang} />
        </div>
      </div>
      {stage === 0 && options ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {options.map((o) => {
            const st = picked !== null ? (o === s.answer ? 'right' : o === picked ? 'wrong' : 'idle') : 'idle'
            return (
              <button key={o} onClick={() => choose(o)} className={`btn min-h-[58px] ${st === 'right' ? 'bg-success text-white' : st === 'wrong' ? 'animate-shake bg-error text-white' : 'bg-card text-ink shadow-soft'}`}>
                {o}
              </button>
            )
          })}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-2">
          <input className={`input text-lg ${picked !== null ? (typedOk ? 'border-success' : 'animate-shake border-error') : ''}`} value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus placeholder={t('write.placeholder')} autoCapitalize="off" autoCorrect="off" spellCheck={false} />
          <button className="btn-primary w-full" disabled={picked !== null}>
            {t('common.check')}
          </button>
          {picked !== null && !typedOk && (
            <p className="text-center font-bold">
              {t('write.correct_answer')}: <span className="text-success">{s.answer}</span>
            </p>
          )}
        </form>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ Write */
function Write({ items, track, reverse, onFinish }: StudyProps) {
  const t = useT()
  const [queue, setQueue] = useState<GameItem[]>(() => shuffle(items))
  const [typed, setTyped] = useState('')
  const [verdict, setVerdict] = useState<'exact' | 'typo' | 'wrong' | null>(null)
  const [done, setDone] = useState(0)
  const retried = useRef(new Set<string>())
  const results = useRef<ResultItem[]>([])
  const start = useRef(Date.now())
  const item = queue[0]
  const s = sidesFor(item, 'write', track, reverse)

  const next = (ok: boolean) => {
    results.current.push(toResult(item, ok))
    let rest = queue.slice(1)
    if (!ok && !retried.current.has(item.key)) {
      retried.current.add(item.key)
      rest = [...rest, item] // one more try at the end
    }
    setDone((d) => d + 1)
    setTyped('')
    setVerdict(null)
    if (!rest.length) onFinish({ results: results.current, durationMs: Date.now() - start.current })
    else setQueue(rest)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (verdict) {
      next(verdict !== 'wrong')
      return
    }
    const v = checkAnswer(typed, s.answer)
    setVerdict(v)
    if (v === 'wrong') feedbackWrong()
    else feedbackCorrect()
  }

  return (
    <div className="space-y-4">
      <ProgressBar value={(done / (items.length + retried.current.size)) * 100} />
      <div className="card space-y-2 p-6 text-center">
        <div className="text-xs font-black uppercase text-muted">{t('study.type')}</div>
        <div className="flex items-center justify-center gap-2">
          <span className="break-words text-3xl font-black">{s.prompt}</span>
          <SpeakButton text={s.prompt} track={track} lang={s.promptLang} />
        </div>
      </div>
      <form onSubmit={submit} className="space-y-2">
        <input
          className={`input text-lg ${verdict === 'wrong' ? 'animate-shake border-error' : verdict ? 'border-success' : ''}`}
          value={typed}
          onChange={(e) => !verdict && setTyped(e.target.value)}
          autoFocus
          placeholder={t('write.placeholder')}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
        />
        {verdict && (
          <div className={`rounded-2xl p-3 text-center font-bold ${verdict === 'wrong' ? 'bg-error/15 text-error' : 'bg-success/15 text-success'}`}>
            {verdict === 'exact' ? t('write.correct') : verdict === 'typo' ? t('write.typo', { answer: s.answer }) : `${t('write.correct_answer')}: ${s.answer}`}
          </div>
        )}
        <button className="btn-primary w-full">{verdict ? t('common.next') : t('common.check')}</button>
        {verdict === 'wrong' && (
          <button type="button" className="btn-ghost w-full" onClick={() => next(true)}>
            <RotateCcw className="h-4 w-4" /> {t('write.override')}
          </button>
        )}
      </form>
    </div>
  )
}
