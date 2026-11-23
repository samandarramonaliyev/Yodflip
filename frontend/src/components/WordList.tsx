import { ArrowRightLeft, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { UserWord } from '../lib/types'
import type { Track } from '../games/types'
import { SpeakButton } from './SpeakButton'
import { AddToDeckSheet } from './WordActions'
import { EmptyState, ErrorState, ListSkeleton, Sheet, toast } from './ui'
import { Link } from 'react-router-dom'

export type ListKind = 'learned' | 'missed' | 'want'

const EMOJI: Record<ListKind, string> = { learned: '✅', missed: '❌', want: '⭐' }

/** One of the three profile word lists: searchable, with delete and move-to-list. */
export function WordList({ which, track }: { which: ListKind; track: Track }) {
  const t = useT()
  const [q, setQ] = useState('')
  const { data, error, loading, reload, setData } = useAsync(() => api.get<UserWord[]>(`/words/lists/${which}/`, { track, q }), [which, track, q])
  const [moving, setMoving] = useState<UserWord | null>(null)
  const [deckOpen, setDeckOpen] = useState(false)

  const remove = async (w: UserWord) => {
    await api.del(`/words/mine/${w.id}/`, { list: which })
    setData((data || []).filter((x) => x.id !== w.id))
    toast.ok(t('lists.removed'))
  }
  const move = async (w: UserWord, to: ListKind) => {
    await api.patch(`/words/mine/${w.id}/`, { to })
    setMoving(null)
    toast.ok(t('lists.moved', { list: t(`lists.${to}`) }))
    void reload()
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
          <input className="input pl-11" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('common.search')} aria-label={t('common.search')} />
        </div>
        {!!data?.length && (
          <Link to={`/play/speed?source=${which}`} className="btn-primary shrink-0">
            ▶ {t('lists.practice')}
          </Link>
        )}
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading ? (
        <ListSkeleton rows={4} height="h-14" />
      ) : !data?.length ? (
        <EmptyState emoji={EMOJI[which]} title={t(`lists.${which}_empty`)} text={t(`lists.${which}_empty_text`)} />
      ) : (
        <ul className="divide-y divide-line rounded-card bg-card shadow-soft">
          {data.map((w) => (
            <li key={w.id} className="flex items-center gap-2 px-3 py-2.5">
              <SpeakButton text={w.term} track={track} className="h-9 w-9" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-black">{w.term}</div>
                <div className="truncate text-sm text-muted">{w.translation_uz || w.definition}</div>
              </div>
              <span className="chip hidden bg-line text-xs sm:inline-flex" title={t('lists.box')}>
                📦 {w.box}/5
              </span>
              <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => setMoving(w)} aria-label={t('lists.move')}>
                <ArrowRightLeft className="h-4 w-4" />
              </button>
              <button className="grid h-10 w-10 place-items-center rounded-full text-error hover:bg-error/10" onClick={() => remove(w)} aria-label={t('common.delete')}>
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Sheet open={moving !== null} onClose={() => setMoving(null)} title={moving?.term}>
        <div className="grid gap-2">
          {(['learned', 'missed', 'want'] as ListKind[])
            .filter((k) => k !== which)
            .map((k) => (
              <button key={k} className="btn-ghost justify-start" onClick={() => moving && move(moving, k)}>
                {EMOJI[k]} {t('lists.move_to', { list: t(`lists.${k}`) })}
              </button>
            ))}
          <button className="btn-ghost justify-start" onClick={() => setDeckOpen(true)}>
            ➕ {t('decks.add_to_deck')}
          </button>
        </div>
        {moving && (
          <AddToDeckSheet
            open={deckOpen}
            onClose={() => {
              setDeckOpen(false)
              setMoving(null)
            }}
            track={track}
            words={[{ term: moving.term, translation: moving.translation_uz, definition: moving.definition, article: moving.article }]}
          />
        )}
      </Sheet>
    </div>
  )
}
