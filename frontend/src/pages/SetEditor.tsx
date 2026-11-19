import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ArrowLeft, Brain, Library, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ErrorState, ListSkeleton, Segmented, Spinner, toast } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useMainButton, useTelegramBack } from '../lib/hooks'
import type { Deck, SetPair, WordSet } from '../lib/types'
import { useApp } from '../store/app'
import type { Track } from '../games/types'

const blank = (): SetPair => ({ word: '', definition: '', part_of_speech: '', article: null, translation_uz: '' })

export default function SetEditor() {
  const { id = 'new' } = useParams()
  const isNew = id === 'new'
  const t = useT()
  const nav = useNavigate()
  useTelegramBack('/sets')
  const loc = useLocation() as { state?: { pairs?: SetPair[]; language?: Track; mismatch?: boolean } }
  const appTrack = useApp((s) => s.track)
  const setAppTrack = useApp((s) => s.setTrack)
  const [name, setName] = useState(() => `${t('sets.page')} ${new Date().toLocaleDateString()}`)
  const [track, setTrack] = useState<Track>(loc.state?.language || appTrack)
  const [pairs, setPairs] = useState<SetPair[]>(() => (loc.state?.pairs?.length ? loc.state.pairs : isNew ? [blank(), blank(), blank(), blank()] : []))
  const [savedId, setSavedId] = useState<number | null>(isNew ? null : Number(id))
  const [loading, setLoading] = useState(!isNew)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(isNew)

  useEffect(() => {
    if (isNew) return
    api
      .get<WordSet>(`/sets/${id}/`)
      .then((s) => {
        setName(s.name)
        setTrack(s.track)
        setPairs(s.pairs || [])
      })
      .catch(setError)
      .finally(() => setLoading(false))
  }, [id, isNew])

  const update = (i: number, patch: Partial<SetPair>) => {
    setPairs((p) => p.map((x, k) => (k === i ? { ...x, ...patch } : x)))
    setDirty(true)
  }
  const valid = pairs.filter((p) => p.word.trim() && p.definition.trim())

  const save = async (): Promise<number | null> => {
    if (!valid.length) {
      toast.err(t('sets.need_pairs'))
      return null
    }
    setBusy(true)
    try {
      const body = { name: name.trim() || t('sets.untitled'), track, pairs: valid.map((p) => ({ ...p, article: p.article || '' })) }
      const s = savedId ? await api.patch<WordSet>(`/sets/${savedId}/`, body) : await api.post<WordSet>('/sets/', body)
      setSavedId(s.id)
      setDirty(false)
      toast.ok(t('common.saved'))
      if (isNew) nav(`/sets/${s.id}`, { replace: true })
      return s.id
    } catch {
      toast.err(t('err.generic'))
      return null
    } finally {
      setBusy(false)
    }
  }

  const playUrl = async (game: string) => {
    const sid = dirty || !savedId ? await save() : savedId
    if (!sid) return
    if (track !== appTrack) setAppTrack(track)
    nav(`/play/${game}?source=set&id=${sid}`)
  }

  const toDeck = async () => {
    const sid = dirty || !savedId ? await save() : savedId
    if (!sid) return
    try {
      const d = await api.post<Deck>(`/sets/${sid}/to-deck/`)
      if (track !== appTrack) setAppTrack(track)
      toast.ok(t('sets.deck_created'))
      nav(`/decks/${d.id}`)
    } catch {
      toast.err(t('err.generic'))
    }
  }

  const remove = async () => {
    if (!savedId || !window.confirm(t('common.confirm_delete'))) return
    await api.del(`/sets/${savedId}/`)
    nav('/sets')
  }

  useMainButton(t('sets.play_match'), () => void playUrl('match'), valid.length > 0 && !busy)

  if (loading) return <div className="page"><ListSkeleton rows={5} /></div>
  if (error) return <div className="page"><ErrorState error={error} /></div>

  return (
    <div className="page max-w-3xl space-y-4">
      <div className="flex items-center gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-full hover:bg-line" onClick={() => nav('/sets')} aria-label={t('common.back')}>
          <ArrowLeft />
        </button>
        <h1 className="h1">{isNew ? t('sets.review_title') : t('sets.edit_title')}</h1>
      </div>
      {isNew && <p className="text-muted">{t('sets.review_hint')}</p>}
      {loc.state?.mismatch && (
        <div className="flex gap-2 rounded-2xl bg-accent/25 p-3 text-sm font-bold">
          <AlertTriangle className="h-5 w-5 shrink-0" /> {t('sets.mismatch', { lang: track.toUpperCase() })}
        </div>
      )}

      <div className="card grid gap-3 p-4 sm:grid-cols-[1fr_auto]">
        <input className="input" value={name} onChange={(e) => { setName(e.target.value); setDirty(true) }} placeholder={t('sets.name')} aria-label={t('sets.name')} />
        <Segmented
          value={track}
          onChange={(v) => { setTrack(v); setDirty(true) }}
          options={[
            { value: 'en', label: '🇬🇧 EN' },
            { value: 'de', label: '🇩🇪 DE' },
          ]}
        />
      </div>

      <ul className="space-y-3">
        <AnimatePresence initial={false}>
          {pairs.map((p, i) => (
            <motion.li key={i} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -30 }} className="card space-y-2 p-3">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary-soft text-xs font-black text-primary">{i + 1}</span>
                {track === 'de' && (
                  <select className="input w-[88px] shrink-0 px-2" value={p.article || ''} onChange={(e) => update(i, { article: e.target.value || null })} aria-label={t('decks.article')}>
                    <option value="">—</option>
                    <option value="der">der</option>
                    <option value="die">die</option>
                    <option value="das">das</option>
                  </select>
                )}
                <input className="input font-extrabold" value={p.word} onChange={(e) => update(i, { word: e.target.value })} placeholder={t('sets.word')} aria-label={t('sets.word')} />
                <button className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-error hover:bg-error/10" onClick={() => { setPairs((x) => x.filter((_, k) => k !== i)); setDirty(true) }} aria-label={t('common.delete')}>
                  <Trash2 className="h-5 w-5" />
                </button>
              </div>
              <textarea className="input font-read min-h-[64px] py-2" value={p.definition} onChange={(e) => update(i, { definition: e.target.value })} placeholder={t('sets.definition', { lang: track.toUpperCase() })} aria-label={t('sets.definition', { lang: track.toUpperCase() })} />
              <div className="grid grid-cols-[1fr_120px] gap-2">
                <input className="input" value={p.translation_uz} onChange={(e) => update(i, { translation_uz: e.target.value })} placeholder={t('sets.translation_uz')} aria-label={t('sets.translation_uz')} />
                <input className="input" value={p.part_of_speech} onChange={(e) => update(i, { part_of_speech: e.target.value })} placeholder={t('sets.pos')} aria-label={t('sets.pos')} />
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>

      <button className="btn-soft w-full" onClick={() => { setPairs((p) => [...p, blank()]); setDirty(true) }}>
        <Plus className="h-5 w-5" /> {t('sets.add_pair')}
      </button>

      <div className="sticky bottom-24 z-10 grid gap-2 rounded-[22px] bg-bg/90 p-2 backdrop-blur sm:grid-cols-2 lg:bottom-4">
        <button className="btn-ghost" onClick={() => void save()} disabled={busy || !dirty}>
          {busy ? <Spinner className="h-5 w-5" /> : <Save className="h-5 w-5" />} {dirty ? t('common.save') : t('common.saved')}
        </button>
        <button className="btn-primary" onClick={() => void playUrl('match')} disabled={busy || !valid.length}>
          🃏 {t('sets.play_match')}
        </button>
        <button className="btn-ghost" onClick={() => void playUrl('speed')} disabled={busy || !valid.some((p) => p.translation_uz)}>
          <Brain className="h-5 w-5" /> {t('sets.play_memorize')}
        </button>
        <button className="btn-ghost" onClick={toDeck} disabled={busy || !valid.length}>
          <Library className="h-5 w-5" /> {t('sets.to_deck')}
        </button>
      </div>
      {savedId && (
        <div className="flex justify-between">
          <Link to="/sets" className="text-sm font-bold text-muted underline">
            {t('sets.title')}
          </Link>
          <button className="text-sm font-bold text-error" onClick={remove}>
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  )
}
