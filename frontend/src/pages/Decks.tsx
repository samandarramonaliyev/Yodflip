import { Globe, Lock, Plus, Search } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, ListSkeleton, Segmented, Sheet, Spinner, Toggle, toast } from '../components/ui'
import { useT } from '../i18n'
import { api } from '../lib/api'
import { useAsync } from '../lib/hooks'
import type { Deck } from '../lib/types'
import { useApp } from '../store/app'

function DeckCard({ d }: { d: Deck }) {
  const t = useT()
  return (
    <Link to={d.is_owner ? `/decks/${d.id}` : `/d/${d.share_code}`} className="card flex flex-col gap-2 p-4 transition hover:shadow-lift">
      <div className="flex items-start justify-between gap-2">
        <span className="line-clamp-2 font-black">{d.name}</span>
        {d.is_public ? <Globe className="h-4 w-4 shrink-0 text-success" /> : <Lock className="h-4 w-4 shrink-0 text-muted" />}
      </div>
      {d.description && <p className="line-clamp-2 text-sm text-muted">{d.description}</p>}
      <div className="mt-auto flex items-center justify-between text-xs font-bold text-muted">
        <span className="chip bg-tint-soft text-ink">{t('decks.cards_n', { n: d.card_count })}</span>
        {!d.is_owner && <span>{d.owner_name}</span>}
      </div>
    </Link>
  )
}

export default function Decks() {
  const t = useT()
  const nav = useNavigate()
  const track = useApp((s) => s.track)
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<'mine' | 'public'>('mine')
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState(params.get('new') === '1')
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [busy, setBusy] = useState(false)
  const mine = useAsync(() => api.get<Deck[]>('/decks/', { track }), [track])
  const pub = useAsync(() => (tab === 'public' ? api.get<Deck[]>('/decks/public/', { track, q }) : Promise.resolve([] as Deck[])), [track, tab, q])

  useEffect(() => {
    if (params.get('new') === '1') {
      setCreating(true)
      params.delete('new')
      setParams(params, { replace: true })
    }
  }, [params, setParams])

  const create = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      const d = await api.post<Deck>('/decks/', { name: name.trim(), description: desc, track, is_public: isPublic })
      toast.ok(t('decks.created'))
      nav(`/decks/${d.id}`)
    } catch {
      toast.err(t('err.generic'))
    } finally {
      setBusy(false)
    }
  }

  const list = tab === 'mine' ? mine : pub
  return (
    <div className="page space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="h1">{t('decks.title')}</h1>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          <Plus className="h-5 w-5" /> <span className="hidden sm:inline">{t('decks.create')}</span>
        </button>
      </div>
      <Segmented
        className="max-w-sm"
        value={tab}
        onChange={setTab}
        options={[
          { value: 'mine', label: t('decks.mine') },
          { value: 'public', label: t('decks.public') },
        ]}
      />
      {tab === 'public' && (
        <div className="relative">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
          <input className="input pl-11" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('common.search')} />
        </div>
      )}
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.loading ? (
        <ListSkeleton rows={4} height="h-28" />
      ) : !list.data?.length ? (
        <EmptyState
          emoji="🗂️"
          title={tab === 'mine' ? t('decks.empty') : t('decks.public_empty')}
          text={tab === 'mine' ? t('decks.empty_text') : undefined}
          action={tab === 'mine' ? <button className="btn-primary" onClick={() => setCreating(true)}>{t('decks.create')}</button> : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.data.map((d) => (
            <DeckCard key={d.id} d={d} />
          ))}
        </div>
      )}

      <Sheet open={creating} onClose={() => setCreating(false)} title={t('decks.create')}>
        <form onSubmit={create} className="space-y-3">
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder={t('decks.name')} autoFocus />
          <textarea className="input min-h-[80px] py-2" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t('decks.description')} />
          <div className="rounded-2xl bg-line/50 px-3 text-sm font-bold">
            {t('decks.track')}: {track === 'en' ? '🇬🇧 English' : '🇩🇪 Deutsch'}
          </div>
          <Toggle checked={isPublic} onChange={setIsPublic} label={t('decks.is_public')} />
          <button className="btn-primary w-full" disabled={busy}>
            {busy && <Spinner className="h-5 w-5" />} {t('decks.create')}
          </button>
        </form>
      </Sheet>
    </div>
  )
}
