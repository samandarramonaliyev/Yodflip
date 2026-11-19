import { BookmarkPlus, Plus, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { speak, ttsSupported } from '../lib/tts'
import type { Deck } from '../lib/types'
import type { Track } from '../games/types'
import { useT } from '../i18n'
import { ListSkeleton, Sheet, toast } from './ui'

export interface WordLike {
  term: string
  translation?: string
  definition?: string
  article?: string
  word_id?: number | null
}

export function SpeakButton({ text, track, className = '' }: { text: string; track: Track; className?: string }) {
  const t = useT()
  if (!ttsSupported()) return null
  return (
    <button
      type="button"
      className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary-soft text-primary ${className}`}
      onClick={(e) => {
        e.stopPropagation()
        speak(text, track)
      }}
      aria-label={t('common.listen')}
    >
      <Volume2 className="h-5 w-5" />
    </button>
  )
}

export async function saveWant(track: Track, w: WordLike, t: (k: string) => string) {
  try {
    await api.post('/words/lists/want/add/', {
      track,
      term: w.term,
      translation_uz: w.translation || '',
      definition: w.definition || '',
      article: w.article || '',
      word_id: w.word_id ?? null,
    })
    toast.ok(t('lists.saved_want'))
  } catch {
    toast.err(t('err.generic'))
  }
}

/** One-tap: save to Want-to-learn, or add to any deck. */
export function WordActions({ word, track }: { word: WordLike; track: Track }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex items-center gap-1">
      <button className="grid h-10 w-10 place-items-center rounded-full bg-accent/25" onClick={() => saveWant(track, word, t)} aria-label={t('lists.add_want')} title={t('lists.add_want')}>
        <BookmarkPlus className="h-5 w-5" />
      </button>
      <button className="grid h-10 w-10 place-items-center rounded-full bg-success/15 text-success" onClick={() => setOpen(true)} aria-label={t('decks.add_to_deck')} title={t('decks.add_to_deck')}>
        <Plus className="h-5 w-5" />
      </button>
      <AddToDeckSheet open={open} onClose={() => setOpen(false)} words={[word]} track={track} />
    </div>
  )
}

export function AddToDeckSheet({ open, onClose, words, track }: { open: boolean; onClose: () => void; words: WordLike[]; track: Track }) {
  const t = useT()
  const [decks, setDecks] = useState<Deck[] | null>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setDecks(await api.get<Deck[]>('/decks/', { track }))
    } catch {
      setDecks([])
    }
  }

  const add = async (deck: Deck) => {
    setBusy(true)
    try {
      for (const w of words) {
        await api.post('/decks/quick-add/', {
          deck_id: deck.id,
          term: w.term,
          translation: w.translation || '',
          definition: w.definition || '',
          article: w.article || '',
        })
      }
      toast.ok(t('decks.added_to', { name: deck.name }))
      onClose()
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (open && decks === null) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <Sheet open={open} onClose={onClose} title={t('decks.add_to_deck')}>
      {decks === null ? (
        <ListSkeleton rows={3} height="h-12" />
      ) : decks.length === 0 ? (
        <div className="space-y-3 text-center">
          <p className="text-muted">{t('decks.none_for_track')}</p>
          <Link to="/decks?new=1" className="btn-primary w-full" onClick={onClose}>
            <Plus className="h-5 w-5" /> {t('decks.create')}
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {decks.map((d) => (
            <li key={d.id}>
              <button disabled={busy} className="flex min-h-[52px] w-full items-center justify-between rounded-2xl bg-line/60 px-4 text-left font-bold hover:bg-line" onClick={() => add(d)}>
                <span className="truncate">{d.name}</span>
                <span className="text-sm text-muted">{t('decks.cards_n', { n: d.card_count })}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  )
}
