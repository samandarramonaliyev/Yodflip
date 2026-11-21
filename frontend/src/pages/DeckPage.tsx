import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Brain,
  Download,
  Layers,
  Link2,
  ListPlus,
  Pencil,
  PenLine,
  Plus,
  Send,
  Trash2,
  Upload,
} from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { SpeakButton } from '../components/WordActions'
import { EmptyState, ErrorState, ListSkeleton, Sheet, Spinner, Toggle, toast } from '../components/ui'
import { GAMES } from '../games/catalog'
import { isAvailable, modeFor } from '../games/direction'
import { useT } from '../i18n'
import { api, ApiError } from '../lib/api'
import { useAsync, useTelegramBack } from '../lib/hooks'
import { shareToTelegram } from '../lib/telegram'
import type { Card, Deck } from '../lib/types'
import { allowedLangs, LANG_META, type TrLang } from '../lib/translation'

const emptyCard = { term: '', translation: '', definition: '', example: '', article: '' }

export default function DeckPage() {
  const { id } = useParams()
  const t = useT()
  const nav = useNavigate()
  useTelegramBack('/decks')
  const { data: deck, error, loading, reload, setData } = useAsync(() => api.get<Deck>(`/decks/${id}/`), [id])
  const [editing, setEditing] = useState<Partial<Card> | null>(null)
  const [image, setImage] = useState<File | null>(null)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulk, setBulk] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [aiBusy, setAiBusy] = useState<TrLang | null>(null)
  const [aiDown, setAiDown] = useState(false)
  const csvRef = useRef<HTMLInputElement>(null)

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>
  if (loading || !deck) return <div className="page"><ListSkeleton rows={6} /></div>

  const cards = deck.cards || []
  const shareUrl = `${window.location.origin}/d/${deck.share_code}`

  const saveCard = async (e: FormEvent) => {
    e.preventDefault()
    if (!editing?.term?.trim() || !editing.translation?.trim()) return
    setBusy(true)
    try {
      const fd = new FormData()
      for (const k of ['term', 'translation', 'definition', 'example', 'article'] as const) fd.append(k, (editing[k] as string) || '')
      if (image) fd.append('image', image)
      if (editing.id) await api.request('PATCH', `/decks/${deck.id}/cards/${editing.id}/`, { form: fd })
      else await api.form(`/decks/${deck.id}/cards/`, fd)
      setEditing(null)
      setImage(null)
      await reload()
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  const delCard = async (c: Card) => {
    if (!window.confirm(t('common.confirm_delete'))) return
    await api.del(`/decks/${deck.id}/cards/${c.id}/`)
    setData({ ...deck, cards: cards.filter((x) => x.id !== c.id), card_count: deck.card_count - 1 })
  }

  const move = async (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= cards.length) return
    const next = cards.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    setData({ ...deck, cards: next })
    await api.post(`/decks/${deck.id}/reorder/`, { ids: next.map((c) => c.id) }).catch(() => toast.err(t('err.generic')))
  }

  const doBulk = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ added: number; bad_lines: number[] }>(`/decks/${deck.id}/bulk/`, { text: bulk })
      toast.ok(t('decks.bulk_added', { n: r.added }))
      if (r.bad_lines.length) toast.info(t('decks.bulk_bad', { lines: r.bad_lines.join(', ') }))
      setBulk('')
      setBulkOpen(false)
      await reload()
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  const importCsv = async (f?: File) => {
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    try {
      const r = await api.form<{ added: number }>(`/decks/${deck.id}/import/`, fd)
      toast.ok(t('decks.bulk_added', { n: r.added }))
      await reload()
    } catch {
      toast.err(t('err.generic'))
    }
  }

  const updateDeck = async (patch: Partial<Deck>) => {
    const d = await api.patch<Deck>(`/decks/${deck.id}/`, patch)
    setData({ ...deck, ...d, cards })
  }

  const share = async (via: 'link' | 'tg') => {
    if (!deck.is_public) {
      if (!window.confirm(t('decks.make_public_confirm'))) return
      await updateDeck({ is_public: true })
    }
    if (via === 'tg') shareToTelegram(shareUrl, t('decks.share_text', { name: deck.name }))
    else {
      try {
        await navigator.clipboard.writeText(shareUrl)
        toast.ok(t('decks.link_copied'))
      } catch {
        window.prompt(t('decks.share_link'), shareUrl)
      }
    }
  }

  const deleteDeck = async () => {
    if (!window.confirm(t('common.confirm_delete'))) return
    await api.del(`/decks/${deck.id}/`)
    nav('/decks')
  }

  const deckLang: TrLang = deck.translation_lang ?? 'uz'
  const otherLangs = allowedLangs(deck.track).filter((l) => l !== deckLang)
  const hasLang = (l: TrLang) => cards.length > 0 && cards.every((c) => c.extra_translations?.[l])
  const aiTranslate = async (l: TrLang) => {
    setAiBusy(l)
    try {
      const d = await api.post<Deck>(`/decks/${deck.id}/translate/`, { lang: l })
      setData({ ...deck, ...d })
      toast.ok(t('decks.ai_done', { lang: LANG_META[l].name }))
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) setAiDown(true)
      else toast.err(t('err.generic'))
    } finally {
      setAiBusy(null)
    }
  }

  const memoGames = GAMES.filter((g) => g.needsSource && isAvailable(g.id, deck.track) && modeFor(g.id) !== 'definition')
  const hasDefs = cards.some((c) => c.definition)

  return (
    <div className="page space-y-4">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 shrink-0 place-items-center rounded-full hover:bg-line" onClick={() => nav('/decks')} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="h1 truncate">{deck.name}</h1>
          <div className="text-sm text-muted">
            {deck.track === 'en' ? 'EN' : 'DE'} → {LANG_META[deckLang].flag} {LANG_META[deckLang].short} · {t('decks.cards_n', { n: cards.length })}
          </div>
        </div>
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => setSettingsOpen(true)} aria-label={t('common.edit')}>
          <Pencil className="h-5 w-5" />
        </button>
      </div>
      {deck.description && <p className="text-muted">{deck.description}</p>}
      {deck.is_owner && cards.length > 0 && (
        <section className="card space-y-2 p-3" data-testid="deck-langs">
          <div className="text-sm font-bold">
            {t('decks.translation_lang')}: {LANG_META[deckLang].flag} {LANG_META[deckLang].name}
          </div>
          <div className="flex flex-wrap gap-2">
            {otherLangs.map((l) =>
              hasLang(l) ? (
                <span key={l} className="chip bg-success/15 text-ink">
                  ✓ {LANG_META[l].flag} {LANG_META[l].short}
                </span>
              ) : (
                <button
                  key={l}
                  className="chip bg-line/70 disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={aiDown || aiBusy !== null}
                  title={aiDown ? t('tr.unavailable') : undefined}
                  onClick={() => void aiTranslate(l)}
                >
                  {aiBusy === l ? <Spinner className="h-4 w-4" /> : '✨'} {t('decks.ai_translate')} → {LANG_META[l].flag} {LANG_META[l].short}
                </button>
              ),
            )}
          </div>
          {aiDown && <p className="text-xs text-muted">{t('tr.unavailable')}</p>}
        </section>
      )}

      {cards.length > 0 && (
        <section className="grid grid-cols-3 gap-2">
          <Link to={`/play/flashcards?source=deck&id=${deck.id}`} className="card flex flex-col items-center gap-1 p-3 text-center font-extrabold hover:shadow-lift">
            <Layers className="h-6 w-6 text-primary" /> {t('study.flashcards')}
          </Link>
          <Link to={`/decks/${deck.id}/study/learn`} className="card flex flex-col items-center gap-1 p-3 text-center font-extrabold hover:shadow-lift">
            <Brain className="h-6 w-6 text-primary" /> {t('study.learn')}
          </Link>
          <Link to={`/decks/${deck.id}/study/write`} className="card flex flex-col items-center gap-1 p-3 text-center font-extrabold hover:shadow-lift">
            <PenLine className="h-6 w-6 text-primary" /> {t('study.write')}
          </Link>
        </section>
      )}
      {cards.length >= 2 && (
        <section className="flex gap-2 overflow-x-auto pb-1">
          {memoGames.map((g) => (
            <Link key={g.id} to={`/play/${g.id}?source=deck&id=${deck.id}`} className="chip shrink-0 bg-card shadow-soft">
              {g.emoji} {t(`game.${g.id}`)}
            </Link>
          ))}
          {hasDefs && (
            <Link to={`/play/match?source=deck&id=${deck.id}`} className="chip shrink-0 bg-card shadow-soft">
              🃏 {t('game.match')}
            </Link>
          )}
        </section>
      )}

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <button className="btn-primary" onClick={() => setEditing({ ...emptyCard })}>
          <Plus className="h-5 w-5" /> {t('decks.add_card')}
        </button>
        <button className="btn-ghost" onClick={() => setBulkOpen(true)}>
          <ListPlus className="h-5 w-5" /> {t('decks.bulk')}
        </button>
        <button className="btn-ghost" onClick={() => share('link')}>
          <Link2 className="h-5 w-5" /> {t('decks.share')}
        </button>
        <button className="btn bg-[#229ED9] text-white" onClick={() => share('tg')}>
          <Send className="h-5 w-5" /> Telegram
        </button>
      </section>

      {cards.length === 0 ? (
        <EmptyState emoji="🃏" title={t('decks.no_cards')} text={t('decks.no_cards_text')} />
      ) : (
        <ul className="grid gap-2 md:grid-cols-2">
          {cards.map((c, i) => (
            <li key={c.id} className="card flex items-start gap-2 p-3">
              {c.image && <img src={c.image} alt="" className="h-14 w-14 shrink-0 rounded-xl object-cover" />}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1">
                  <span className="break-words font-black">{c.article && !c.term.toLowerCase().startsWith(c.article) ? `${c.article} ` : ''}{c.term}</span>
                  <SpeakButton text={c.term} track={deck.track} className="h-8 w-8 scale-90" />
                </div>
                <div className="font-bold text-primary">{c.translation}</div>
                {Object.entries(c.extra_translations || {}).map(([l, v]) => (
                  <div key={l} className="text-xs text-muted">
                    {LANG_META[l as TrLang]?.flag} {v}
                  </div>
                ))}
                {c.definition && <div className="font-read text-sm text-muted">{c.definition}</div>}
                {c.example && <div className="font-read text-xs italic text-muted">“{c.example}”</div>}
              </div>
              <div className="flex shrink-0 flex-col items-center">
                <button className="grid h-9 w-9 place-items-center rounded-full hover:bg-line disabled:opacity-30" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Up">
                  <ArrowUp className="h-4 w-4" />
                </button>
                <button className="grid h-9 w-9 place-items-center rounded-full hover:bg-line" onClick={() => setEditing(c)} aria-label={t('common.edit')}>
                  <Pencil className="h-4 w-4" />
                </button>
                <button className="grid h-9 w-9 place-items-center rounded-full text-error hover:bg-error/10" onClick={() => delCard(c)} aria-label={t('common.delete')}>
                  <Trash2 className="h-4 w-4" />
                </button>
                <button className="grid h-9 w-9 place-items-center rounded-full hover:bg-line disabled:opacity-30" onClick={() => move(i, 1)} disabled={i === cards.length - 1} aria-label="Down">
                  <ArrowDown className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" onClick={() => api.download(`/decks/${deck.id}/export/`, `${deck.name}.csv`)}>
          <Download className="h-5 w-5" /> {t('decks.export_csv')}
        </button>
        <button className="btn-ghost" onClick={() => csvRef.current?.click()}>
          <Upload className="h-5 w-5" /> {t('decks.import_csv')}
        </button>
        <input ref={csvRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => importCsv(e.target.files?.[0])} />
      </div>

      {/* Add / edit card */}
      <Sheet open={editing !== null} onClose={() => setEditing(null)} title={editing?.id ? t('decks.edit_card') : t('decks.add_card')}>
        {editing && (
          <form onSubmit={saveCard} className="space-y-3">
            <div className="flex gap-2">
              {deck.track === 'de' && (
                <select className="input w-[92px] shrink-0 px-2" value={editing.article || ''} onChange={(e) => setEditing({ ...editing, article: e.target.value })} aria-label={t('decks.article')}>
                  <option value="">—</option>
                  <option value="der">der</option>
                  <option value="die">die</option>
                  <option value="das">das</option>
                </select>
              )}
              <input className="input font-bold" required value={editing.term || ''} onChange={(e) => setEditing({ ...editing, term: e.target.value })} placeholder={t('decks.term')} autoFocus />
            </div>
            <input className="input" required value={editing.translation || ''} onChange={(e) => setEditing({ ...editing, translation: e.target.value })} placeholder={`${t('decks.translation')} (${LANG_META[deckLang].name})`} />
            <textarea className="input font-read min-h-[64px] py-2" value={editing.definition || ''} onChange={(e) => setEditing({ ...editing, definition: e.target.value })} placeholder={t('decks.definition_opt')} />
            <input className="input" value={editing.example || ''} onChange={(e) => setEditing({ ...editing, example: e.target.value })} placeholder={t('decks.example_opt')} />
            <label className="flex min-h-[48px] cursor-pointer items-center gap-2 rounded-2xl border border-dashed border-line px-4 text-sm font-bold text-muted">
              <Upload className="h-4 w-4" /> {image ? image.name : t('decks.image_opt')}
              <input type="file" accept="image/*" className="hidden" onChange={(e) => setImage(e.target.files?.[0] || null)} />
            </label>
            <button className="btn-primary w-full" disabled={busy}>
              {busy && <Spinner className="h-5 w-5" />} {t('common.save')}
            </button>
          </form>
        )}
      </Sheet>

      {/* Bulk add */}
      <Sheet open={bulkOpen} onClose={() => setBulkOpen(false)} title={t('decks.bulk')}>
        <p className="mb-2 text-sm text-muted">{t('decks.bulk_hint')}</p>
        <textarea
          className="input font-read min-h-[200px] py-2"
          value={bulk}
          onChange={(e) => setBulk(e.target.value)}
          placeholder={deck.track === 'de' ? 'der Hund - it\ndie Katze: mushuk\nlaufen\tyugurmoq' : 'apple - olma\nbook: kitob\nto run\tyugurmoq'}
        />
        <button className="btn-primary mt-3 w-full" disabled={busy || !bulk.trim()} onClick={doBulk}>
          {busy && <Spinner className="h-5 w-5" />} {t('decks.bulk_add_btn')}
        </button>
      </Sheet>

      {/* Settings */}
      <Sheet open={settingsOpen} onClose={() => setSettingsOpen(false)} title={t('decks.settings')}>
        <DeckSettings deck={deck} onSave={async (p) => { await updateDeck(p); setSettingsOpen(false) }} onDelete={deleteDeck} />
      </Sheet>
    </div>
  )
}

function DeckSettings({ deck, onSave, onDelete }: { deck: Deck; onSave: (p: Partial<Deck>) => Promise<void>; onDelete: () => void }) {
  const t = useT()
  const [name, setName] = useState(deck.name)
  const [description, setDescription] = useState(deck.description)
  const [isPublic, setIsPublic] = useState(deck.is_public)
  return (
    <div className="space-y-3">
      <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t('decks.name')} />
      <textarea className="input min-h-[80px] py-2" value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('decks.description')} />
      <Toggle checked={isPublic} onChange={setIsPublic} label={t('decks.is_public')} />
      <button className="btn-primary w-full" onClick={() => onSave({ name, description, is_public: isPublic })}>
        {t('common.save')}
      </button>
      <button className="btn-danger w-full" onClick={onDelete}>
        <Trash2 className="h-5 w-5" /> {t('decks.delete')}
      </button>
    </div>
  )
}
