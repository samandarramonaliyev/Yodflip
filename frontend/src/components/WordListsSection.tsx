import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRightLeft, ChevronDown, ChevronUp, Search, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Track } from '../games/types'
import { useT } from '../i18n'
import { api } from '../lib/api'
import type { Deck, UserWord } from '../lib/types'
import { SpeakButton } from './SpeakButton'
import { EmptyState, Sheet, Spinner, toast } from './ui'

export type ListKind = 'learned' | 'want' | 'missed'
export const COLLAPSED_COUNT = 6
export const PAGE_SIZE = 30

const EMOJI: Record<ListKind, string> = { learned: '✅', want: '⭐', missed: '❌' }
const TAB_KEY: Record<ListKind, string> = { learned: 'wl.learned', want: 'wl.want', missed: 'wl.missed' }

type Row = UserWord & { level?: string }
interface Page {
  count: number
  has_more: boolean
  counts: Record<ListKind, number>
  results: Row[]
}

const STORE = 'wf.wl.expanded'
function loadExpanded(): Record<string, boolean> {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) || '{}')
  } catch {
    return {}
  }
}
function saveExpanded(v: Record<string, boolean>) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(v))
  } catch {
    /* private mode */
  }
}

/**
 * Profile word lists as tabs. Collapsed (default): the 6 most recent words + "Hammasini ko'rish (N)".
 * Expanded: search / sort / level / deck filters, 30 rows per request, row actions, "Yopish" on top
 * and at the bottom (sticky on mobile). The open/closed state is remembered per tab for the session.
 */
export function WordListsSection({ track }: { track: Track }) {
  const t = useT()
  const [tab, setTab] = useState<ListKind>('learned')
  const [expanded, setExpanded] = useState<Record<string, boolean>>(loadExpanded)
  const [counts, setCounts] = useState<Record<ListKind, number> | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<'new' | 'az'>('new')
  const [level, setLevel] = useState('')
  const [deck, setDeck] = useState('')
  const [decks, setDecks] = useState<Deck[]>([])
  const [moving, setMoving] = useState<Row | null>(null)
  const header = useRef<HTMLDivElement>(null)
  const open = Boolean(expanded[tab])

  const load = useCallback(
    async (p: number, append: boolean) => {
      setLoading(true)
      try {
        const r = await api.get<Page>('/me/words/', {
          list: tab,
          track,
          page: p,
          page_size: open ? PAGE_SIZE : COLLAPSED_COUNT,
          search: open ? search : '',
          sort: open ? sort : 'new',
          level: open ? level : '',
          deck: open ? deck : '',
        })
        setCounts(r.counts)
        setTotal(r.count)
        setHasMore(r.has_more)
        setPage(p)
        setRows((old) => (append ? [...old, ...r.results] : r.results))
      } catch {
        toast.err(t('err.generic'))
      } finally {
        setLoading(false)
      }
    },
    [tab, track, open, search, sort, level, deck, t],
  )

  useEffect(() => {
    const id = setTimeout(() => void load(1, false), search ? 250 : 0)
    return () => clearTimeout(id)
  }, [load, search])

  useEffect(() => {
    if (!open || decks.length) return
    api
      .get<Deck[]>('/decks/', { track })
      .then(setDecks)
      .catch(() => null)
  }, [open, track, decks.length])

  const setOpen = (v: boolean) => {
    const next = { ...expanded, [tab]: v }
    setExpanded(next)
    saveExpanded(next)
    if (!v) header.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  const remove = async (w: Row) => {
    await api.del(`/words/mine/${w.id}/`, { list: tab })
    toast.ok(t('lists.removed'))
    void load(1, false)
  }
  const move = async (w: Row, to: ListKind) => {
    await api.patch(`/words/mine/${w.id}/`, { to })
    setMoving(null)
    toast.ok(t('lists.moved', { list: t(`lists.${to}`) }))
    void load(1, false)
  }

  const closeBtn = (sticky: boolean) => (
    <button
      className={`btn-ghost w-full ${sticky ? 'sticky bottom-20 z-10 bg-card shadow-soft lg:static lg:shadow-none' : ''}`}
      onClick={() => setOpen(false)}
      data-testid={sticky ? 'close-bottom' : 'close-top'}
    >
      <ChevronUp className="h-5 w-5" /> {t('wl.close')}
    </button>
  )

  return (
    <section className="space-y-3 scroll-mt-20" data-testid="word-lists">
      <div ref={header} className="flex items-center justify-between gap-2">
        <h2 className="h2">{t('lists.title')}</h2>
        {(tab === 'want' || tab === 'missed') && total > 0 && (
          <Link to={`/play/flashcards?source=${tab}`} className="btn-soft min-h-[40px] px-3 text-sm">
            🎴 {t('wl.study')}
          </Link>
        )}
      </div>
      <div className="flex gap-1 overflow-x-auto rounded-2xl bg-line/50 p-1" role="tablist">
        {(['learned', 'want', 'missed'] as ListKind[]).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={`min-h-[40px] flex-1 whitespace-nowrap rounded-xl px-2 text-sm font-extrabold ${tab === k ? 'bg-card shadow-soft' : 'text-muted'}`}
          >
            {EMOJI[k]} {t(TAB_KEY[k])} <span data-testid={`count-${k}`}>({counts?.[k] ?? '…'})</span>
          </button>
        ))}
      </div>

      {!open ? (
        <div className="space-y-2" data-testid="collapsed">
          {loading && !rows.length ? (
            <Spinner className="mx-auto h-6 w-6 text-primary" />
          ) : !rows.length ? (
            <EmptyState emoji={EMOJI[tab]} title={t(`lists.${tab}_empty`)} text={t(`lists.${tab}_empty_text`)} />
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {rows.slice(0, COLLAPSED_COUNT).map((w) => (
                <li key={w.id} className="truncate rounded-2xl bg-card px-3 py-2 text-sm shadow-soft" data-testid="word-chip">
                  <span className="font-black">{w.term}</span>
                  {w.translation_uz && <span className="text-muted"> · {w.translation_uz}</span>}
                </li>
              ))}
            </ul>
          )}
          {total > 0 && (
            <button className="btn-ghost w-full" onClick={() => setOpen(true)} data-testid="expand">
              {t('wl.show_all', { n: total })} <ChevronDown className="h-5 w-5" />
            </button>
          )}
        </div>
      ) : null}

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-3 overflow-hidden"
            data-testid="expanded"
          >
            {closeBtn(false)}
            <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto_auto]">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
                <input className="input pl-11" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('wl.search')} aria-label={t('wl.search')} />
              </div>
              <select className="input" value={sort} onChange={(e) => setSort(e.target.value as 'new' | 'az')} aria-label={t('wl.sort')}>
                <option value="new">{t('wl.sort_new')}</option>
                <option value="az">A–Z</option>
              </select>
              <select className="input" value={level} onChange={(e) => setLevel(e.target.value)} aria-label={t('wl.level')}>
                <option value="">{t('wl.all_levels')}</option>
                {['A1', 'A2', 'B1', 'B2', 'C1'].map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
              <select className="input" value={deck} onChange={(e) => setDeck(e.target.value)} aria-label={t('wl.deck')}>
                <option value="">{t('wl.all_decks')}</option>
                {decks.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-xs font-bold text-muted" data-testid="expanded-total">
              {t('wl.total', { n: total })}
            </div>
            {!rows.length && !loading ? (
              <EmptyState emoji="🔍" title={t('wl.nothing')} />
            ) : (
              <ul className="grid gap-2 lg:grid-cols-2" data-testid="rows">
                {rows.map((w) => (
                  <li key={w.id} className="flex items-center gap-2 rounded-2xl bg-card px-2 py-1.5 shadow-soft" data-testid="word-row">
                    <SpeakButton text={w.term} track={track} className="h-9 w-9" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-black">
                        {w.term} {w.level && <span className="text-xs font-bold text-muted">· {w.level}</span>}
                      </div>
                      <div className="truncate text-xs text-muted">{w.translation_uz || w.definition}</div>
                    </div>
                    <button className="grid h-9 w-9 shrink-0 place-items-center rounded-full hover:bg-line" onClick={() => setMoving(w)} aria-label={t('lists.move')}>
                      <ArrowRightLeft className="h-4 w-4" />
                    </button>
                    <button className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-error hover:bg-error/10" onClick={() => void remove(w)} aria-label={t('common.delete')}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {hasMore && (
              <button className="btn-soft w-full" disabled={loading} onClick={() => void load(page + 1, true)} data-testid="load-more">
                {loading ? <Spinner className="h-5 w-5" /> : null} {t('wl.load_more')}
              </button>
            )}
            {closeBtn(true)}
          </motion.div>
        )}
      </AnimatePresence>

      <Sheet open={moving !== null} onClose={() => setMoving(null)} title={moving?.term}>
        <div className="grid gap-2">
          {(['learned', 'want', 'missed'] as ListKind[])
            .filter((k) => k !== tab)
            .map((k) => (
              <button key={k} className="btn-ghost justify-start" onClick={() => moving && void move(moving, k)}>
                {EMOJI[k]} {t('lists.move_to', { list: t(`lists.${k}`) })}
              </button>
            ))}
        </div>
      </Sheet>
    </section>
  )
}
