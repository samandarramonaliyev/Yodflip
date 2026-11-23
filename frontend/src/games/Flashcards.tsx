import { AnimatePresence, motion, type PanInfo } from 'framer-motion'
import { Check, RotateCcw, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FlipCard } from '../components/FlipCard'
import { FillerBadge } from '../components/LevelProgress'
import { SpeakButton } from '../components/WordActions'
import { Toggle } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { feedbackCorrect, feedbackWrong } from '../lib/fx'
import { toResult, type GameItem, type GameProps, type ResultItem } from './types'

const ARTICLE_COLOR: Record<string, string> = { der: 'text-sky-600', die: 'text-rose-500', das: 'text-emerald-600' }

function newId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
}

/** Card id of a deck item ("c12" -> 12) so the deck's own known / learning stats are updated. */
export function cardIdOf(item: GameItem): number | null {
  return /^c\d+$/.test(item.key) ? Number(item.key.slice(1)) : null
}

function ForeignSide({ item, track }: { item: GameItem; track: 'en' | 'de' }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-[24px] bg-card p-5 text-center shadow-lift" data-testid="card-back">
      <span className="break-words text-3xl font-black">
        {item.article && <span className={ARTICLE_COLOR[item.article] ?? ''}>{item.article} </span>}
        {item.word || item.term}
      </span>
      {item.pos && <span className="text-xs font-bold uppercase tracking-wide text-muted">{item.pos}</span>}
      {item.example && <span className="font-read text-sm italic text-muted">“{item.example}”</span>}
      {item.collocations && <span className="text-xs font-bold">🔗 {item.collocations}</span>}
      <SpeakButton text={item.term} track={track} />
    </div>
  )
}

function TranslationSide({ item }: { item: GameItem }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-[24px] bg-tint p-5 text-center text-tint-ink shadow-lift" data-testid="card-front">
      <span className="break-words text-3xl font-black">{item.translation}</span>
      <SpeakButton text={item.translation} track="en" lang={item.translation_lang ?? 'uz'} />
    </div>
  )
}

export interface FlashcardsProps extends GameProps {
  /** Level round session, so a found word is tied to this round (XP once). */
  sessionId?: string | null
}

/**
 * Two-sided flashcards. Front = translation (chosen language), back = the foreign word.
 * "Topdim" / "Topa olmadim" appear only after the first flip; every answer is saved on the
 * server right away (idempotent client_id) and can be undone ("Bekor qilish").
 */
export default function Flashcards({ items, track, onFinish, sessionId }: FlashcardsProps) {
  const t = useT()
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [seenBack, setSeenBack] = useState(false)
  // Front = translation by default; "Teskari" in the header shows the foreign word first.
  const [teskari, setTeskari] = useState(false)
  const [dir, setDir] = useState<1 | -1>(1)
  const results = useRef<ResultItem[]>([])
  const answers = useRef<Promise<number | null>[]>([])
  const start = useRef(Date.now())
  const done = useRef(false)
  const item = items[idx]

  const flip = useCallback(() => {
    setFlipped((f) => !f)
    setSeenBack(true)
  }, [])

  const answer = useCallback(
    (known: boolean) => {
      if (!seenBack || !item || done.current) return
      if (known) feedbackCorrect(null)
      else feedbackWrong()
      results.current.push(toResult(item, known))
      answers.current.push(
        api
          .post<{ answer_id: number }>('/words/flash/answer/', {
            client_id: newId(),
            track,
            known,
            card_id: cardIdOf(item),
            session_id: sessionId || null,
            item: {
              term: item.term,
              word_id: item.word_id,
              translation: item.translation,
              translation_lang: item.translation_lang ?? 'uz',
              definition: item.definition,
              article: item.article,
            },
          })
          .then((r) => r.answer_id)
          .catch(() => null),
      )
      setDir(known ? 1 : -1)
      if (idx + 1 >= items.length) {
        done.current = true
        onFinish({ results: results.current, durationMs: Date.now() - start.current })
        return
      }
      setIdx(idx + 1)
      setFlipped(false)
      setSeenBack(false)
    },
    [seenBack, item, idx, items.length, onFinish, track, sessionId],
  )

  const undo = useCallback(async () => {
    if (!results.current.length || done.current) return
    results.current.pop()
    const id = await answers.current.pop()
    if (id) await api.post('/words/flash/undo/', { answer_id: id }).catch(() => null)
    setDir(-1)
    setIdx((i) => Math.max(0, i - 1))
    setFlipped(false)
    setSeenBack(false)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      if (e.code === 'Space') {
        e.preventDefault()
        flip()
      } else if (e.key === 'ArrowRight') answer(true)
      else if (e.key === 'ArrowLeft') answer(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [flip, answer])

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (!seenBack) return
    if (info.offset.x > 90) answer(true)
    else if (info.offset.x < -90) answer(false)
  }

  if (!item) return null
  const front = teskari ? <ForeignSide item={item} track={track} /> : <TranslationSide item={item} />
  const back = teskari ? <TranslationSide item={item} /> : <ForeignSide item={item} track={track} />

  return (
    <div className="mx-auto w-full max-w-md space-y-4" data-testid="flashcards">
      <div className="flex items-center justify-between gap-2">
        <button className="chip bg-line/70 disabled:opacity-40" onClick={() => void undo()} disabled={idx === 0} aria-label={t('flash.undo')}>
          <Undo2 className="h-4 w-4" /> {t('flash.undo')}
        </button>
        <Toggle checked={teskari} onChange={setTeskari} label={t('flash.reverse')} />
      </div>
      <div>
        <div className="mb-1 text-center text-sm font-extrabold text-muted" data-testid="flash-progress">
          {idx + 1} / {items.length}
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-line">
          <motion.div className="h-full rounded-full bg-primary" animate={{ width: `${(100 * idx) / items.length}%` }} transition={{ duration: 0.3 }} />
        </div>
      </div>

      <AnimatePresence mode="wait" custom={dir}>
        <motion.div
          key={item.key + idx}
          initial={{ x: 60 * dir, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -60 * dir, opacity: 0 }}
          transition={{ duration: 0.2 }}
          drag={seenBack ? 'x' : false}
          dragConstraints={{ left: 0, right: 0 }}
          onDragEnd={onDragEnd}
          className="relative"
        >
          {item.is_filler && <FillerBadge className="absolute left-3 top-3 z-10" />}
          <button className="block h-[340px] w-full" onClick={flip} aria-label={t('flash.flip')} aria-pressed={flipped} data-testid="flash-card">
            <FlipCard className="h-full w-full" flipped={flipped} duration={0.4} front={front} back={back} />
          </button>
        </motion.div>
      </AnimatePresence>

      {seenBack ? (
        <div className="grid grid-cols-2 gap-3" data-testid="answer-buttons">
          <button className="btn min-h-[56px] bg-[#FF7675] text-white" onClick={() => answer(false)}>
            <X className="h-5 w-5" /> {t('flash.missed')}
          </button>
          <button className="btn min-h-[56px] bg-success text-white" onClick={() => answer(true)}>
            <Check className="h-5 w-5" /> {t('flash.known')}
          </button>
        </div>
      ) : (
        <p className="flex items-center justify-center gap-2 text-sm font-bold text-muted">
          <RotateCcw className="h-4 w-4" /> {t('flash.tap_to_flip')}
        </p>
      )}
    </div>
  )
}
